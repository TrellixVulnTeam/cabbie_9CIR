
# TODO i think maybe we need this to be in a class that get knows what stage this is?

import re
import os
import boto3
import json
from shutil import copy

from common.files import file_bytes
from common.files import file_string
from common.files import file_obj
from common.files import file_json

from common.dicts import fwalk_dict
from common.dicts import fwalk_dict_2
from common.dicts import dict_append
from common.dicts import dict_dotval

from common.lists import ins

from aws.resources import s3
from aws.resources import cloudfront
#from aws.resources import boto_try

from aws.resources import DependecyNotMetError

SERVICES = {
    'cloudfront': {
        'distribution': cloudfront.distribution
    },
    's3': {
        'bucket': s3.bucket,
        'object': s3.object
    }
}


class cloud_app:

    def __init__(self, stage, config_file=".cabbie/config.json"):
        self.project_home = self.__project_home(config_file)
        self.active_stage = stage
        self.config = file_json('/'.join([self.project_home, config_file]))
        self.__live_resource_file = '@/.cabbie/{stage}/resources.json'.format(stage=self.active_stage)
        self.live_resources = self.__open_live_resources()
        
        # TODO: Maybe instead, load stage_vars into a dict and then have a method to return the values as needed?
        self.aws_profile = self.__stage_vars()['aws_profile']
        self.session = boto3.session.Session(profile_name=self.aws_profile)

        self.clients = { # TODO: is this needed?
            'iam': self.session.client('iam'),
            'ddb': self.session.client('dynamodb'),
            'lambda': self.session.client('lambda'),
            'apigateway': self.session.client('apigateway'),
            'cognito': self.session.client('cognito-idp'),
            'sts': self.session.client('sts'),
            's3' : self.session.client('s3')
        }

        # TODO: can use other response items for tracking?
        self.account_id = self.clients['sts'].get_caller_identity()['Account']

        self.resource_template = self.__open_file(
            self.config['template'],
            fopen=file_json,
            copy_forward=True
        )
    

    # init actions
    def __open_live_resources(self):
        # TODO make this use __open_file?
        live_resources = {}
        try:
            #live_resources = file_json(self.__live_resource_file)
            live_resources = self.__open_file(
                self.__live_resource_file,
                fopen=file_json,
                copy_forward=False
            )
            print('opening {} resource file'.format(self.active_stage))
        except Exception as e:
            print(e)
            print('failed to open {} resource file'.format(self.active_stage))
        
        return live_resources


    def __stage_vars(self):
        return self.__open_file(
            '@/.cabbie/.local/stage_vars.json',
            fopen=file_json,
            copy_forward=False
        )[self.active_stage]


    # basic helpers
    def __open_file(self, filename, fopen=file_bytes, copy_forward=False): #fopen=file_string
        """takes a filename, an optonal open function, and an option to copy the file forward to the next stage"""
        filepath = self.__full_path(filename)
        active_filepath = self.__full_path(self.active_stage_filename(filename))
        previous_filepath = self.__full_path(self.previous_stage_filename(filename))

        # print(filepath)
        # print(active_filepath)
        # print(previous_filepath)

        # if copy is true, we want to copy the file to the next 
        if copy_forward:
            self.__ensure_valid_path(active_filepath) # if we're copying the file for the first time the path to the file might nto exist...
            copy(previous_filepath, active_filepath)

        return fopen(active_filepath)


    def __full_path(self, filename, *prefix):
        """takes a filename and returns the full path of the file within the project
        @/ = project home
        """
        # TODO: eventually make the structure more flexible?
        if not prefix:
            prefix = self.project_home
        else:
            prefix = '/'.join(prefix)

        filename = self.__alias(filename)
            

        if '@' in filename: # 'absolute' path
            return filename.replace('@/', '{}/'.format(self.project_home))
        
        # TODO if not given an 'absolute' path, we need to establish where we are in the project 
        return filename


    def __project_home(self, config_file):
        """gets the absolute path of the project home directory, or throws an error if not found"""
        current_path = re.split(r'[/\\]', os.getcwd())  # will this break on paths w/ spaces?  those might have escape chars
        config_path = []

        while current_path:
            config_path = current_path + [config_file]
            if not os.path.exists('/'.join(config_path)):
                current_path.pop()
            else:
                return '/'.join(current_path)

    
    def __alias(self, filename):
        # replace all instances of all aliases... no reason why you cant have an alias in the middle?
        for a in self.config['alias'].keys():
            alias = '@{}'.format(a) # prepend @ before substituting
            filename = filename.replace(alias, self.config['alias'][a])

        return filename


    def __ensure_valid_path(self, filename):
        # make sure all of the necessary directories exist
        path = ''
        for path_dir in filename.split('/')[0:-1]:
            path = '{}/{}'.format(path, path_dir) if path else path_dir
            try:
                os.mkdir(path)
            except:
                pass


    # core functions
    def update_live_resources(self, new_data):
        self.live_resources = {**self.live_resources, **new_data}
        
        out_path = self.__full_path(self.__live_resource_file)
        with open(out_path, 'w') as outfile:
            outfile.write(json.dumps(self.live_resources, indent=4))

    # getters
    def previous_stage(self, stage='', config=''): #TODO should these just point to self? do we need to let users pass in as params?
        if not stage:
            stage = self.active_stage
        if not config:
            config = self.config

        prev_stage_index = config['stages'].index(stage) - 1
        if prev_stage_index < 0:
            return ''
        return config['stages'][prev_stage_index]


    def previous_stage_filename(self, filename):
        if self.previous_stage():
            base_filename = filename.replace(self.config['infrastructure_home'], '@/.cabbie/{}')
            return base_filename.format(self.previous_stage(), filename)
        else:
            return filename


    def active_stage_filename(self, filename):
        # if there is no previous stage, then the "prev stage file" will be pointing to something in the "infrastructure" folder, not in the .cabbie/stage folder
        # replace 'infrastructure' with .cabbie/dev
        base_filename = filename.replace(self.config['infrastructure_home'], '@/.cabbie/{}')
        
        return base_filename.format(self.active_stage)


    # cabbie actions
    def build(self):
        # construct build queue
        build_queue = []
        for name, resource_data in self.resource_template.items(): # TODO: should modify be separate
            service = resource_data['service']
            resource_type = resource_data['type']
            #print('SERVICES[{}][{}]'.format(service, resource_type))
            #print(SERVICES['s3']['bucket'])
            try:
                build_queue.append(SERVICES[service][resource_type](
                    self.session,
                    name=name,
                    attributes=self.__template_item(resource_data),
                    resource_template=resource_data,
                    verbose=True
                ))
            except Exception as e:
                print(service, "not implemented")
        
        print(build_queue)

        # iterate through build queue, run build
        while len(build_queue) > 0:
            try:
                updated_attr = self.resource_template[build_queue[0].name()]
                for response in build_queue[0].build(attributes=self.__template_item(updated_attr)):
                    self.update_live_resources(response)
                    #self.live_resources = { **self.live_resources, **response }  
                    #save_live_resources(active_stage, live_resources)

                build_queue.pop(0)
            except DependecyNotMetError as e:
                # if dependency not met, move to the back of the queue
                build_queue.append(build_queue.pop(0))


        # construct update queue


        # iterate through update queue, run update


    def update(self):
        pass


    def destroy(self):
        pass

 
    # cabbie action helpers
    def __resource_attribute(self, resource_name): 
        #return dict_dotval(live_resources, attr)
        return self.live_resources[resource_name]


    def __session_data(self, var):
        # TODO: make this smarter and add more data about active session... acct_id?  user who made change? date? stuff?
        if var == 'stage':
            return self.active_stage 
        if var == 'account_id':
            return self.account_id


    def __force_bytes(self, string, encoding='utf-8'): #TODO might need to replace/rename/expand if we need to make more things into bytes...
        if isinstance(string, bytes): # string might already be bytes...
            return string

        return bytes(string, encoding)


    def __force_string(self, b, encoding='utf-8'): # TODO might need to replace/rename/expand if we need to make more things into strings...
        return b.decode(encoding)


    def __temp_open_file(self, filename, prefix='@/infrastructure', f=file_bytes): # TODO replace when we decide how to handle files in resource... we'll probably just require fullpaths?
        return this.__open_file(
                '/'.join([prefix, filename]),
                fopen=f,
                copy_forward=True
            )


    def __evaluate(self, string):
        functions = {
            'file': self.__temp_open_file,
            'string': self.__force_string,
            'bytes': self.__force_bytes,
            'resource': self.__resource_attribute,
            'session': self.__session_data,
            'eval': self.__evaluate
        }
        #print('evaluating ', string)

        # if string is not actually a string (eg. int), don't evaluate
        if not isinstance(string, str):
            return string

        # find all expressions to evaluate
        pattern = r"\${[A-Za-z0-9.:'/_-]+}"
        try:
            matches = re.findall(pattern, string)
            for match in matches:
                actions, val = match[2:-1].split(':') #trim off the '${' and '}'
                
                if 'bytes' in actions: # TODO: we run into issues with substituting bytes objects into a string... this might not be the smartest way to handle this
                    if len(matches) > 1:
                        raise ValueError("Bytes-like objects must evaluated alone.") # TODO: reword this error message

                if actions.split('.')[0] in ['resource']: # we might have other data accessors... vars?
                    action, keys = actions.split('.', 1) 
                    val = dict_dotval(functions[action](val), keys) # TODO: this feels hardcode-y
                else:
                    for action in actions.split('.'): # execute list of actions one by one
                        val = functions[action](val)

                if 'bytes' in actions: # TODO: this seems too hardcode-y
                    return val
                string = string.replace(match, val)

        except Exception as e:
            print(e)

        #print(string)
        return string


    def __template_item(self, item):
        # TODO: validate template item
        # TODO: evaluate vals that as needed
        #keys = list(item.keys())
        #key = keys[0] #TODO: make sure there is only 1!
        #attr = item[key]['attributes']

        return fwalk_dict(item['attributes'], f=self.__evaluate)


    def resource_dependencies(self):  # Probably not needed
        dependency_mapping = {}

        pattern_resource = r"\${resource[A-Za-z0-9.:'/_-]+}"
        pattern_filestring = r"\${file.string.eval[A-Za-z0-9.:'/_-]+}"
        def add_dependency(string, key_crumbs):
            """looks for strings like "${resource.<property>:<resource_name>} in resource template, then adds it to the dependency mapping"""
            # need to look into files for resources too!
            if re.fullmatch(pattern_filestring, string):
                # print(string.split(':')[1][:-1])
                # print(self.__full_path(string.split(':')[1][:-1]))
                string = self.__open_file(
                    '@infra/' + string.split(':')[1][:-1],  # this is hardcode-y... need a permanent solution, probably in fullpath
                    fopen=file_string,
                    copy_forward=False
                )
                # print(string)

            matches = re.findall(pattern_resource, string)
            for match in matches:
                resource = match.split(':')[1][:-1] # resource name should be after the colon, need to shave off trailing '}'
                dict_append(dependency_mapping, key_crumbs[0], resource) # key_crumbs[0] is the top level key in our recursive fwalk_dict
            
        fwalk_dict_2(self.resource_template, f=add_dependency)

        return dependency_mapping


    def build_order(self):  # Probably not needed
        to_build = list(self.resource_template.keys())
        order = []
        dependencies = self.resource_dependencies()

        while to_build:
            if to_build[0] not in dependencies.keys():
                order.append(to_build.pop(0))
            elif ins(order, dependencies[to_build[0]]):
                order.append(to_build.pop(0))
            else:
                to_build.append(to_build.pop(0))

        return order
