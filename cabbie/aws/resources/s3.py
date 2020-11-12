"""
General flow:  We open up the resource_template.json in the main method.  For each resource, create a
corresponding resource object and add to the build queue, modify queue.  attempt to build one by one.  if
dependecies not met, throw error.  catch error, move to back of queue.  repeat for modify.
"""

import boto3

from .resources import dependency
from .resources import DependecyNotMetError
from .resources import resource

from common.files import file_obj
from common.files import list_dir


from common.dicts import dict_select
from common.dicts import dict_dotval
from common.dicts import safe_dict_val


# TODO: come up with a way to template-ize functions?
# TODO: add verbose print statements
# TODO: add option to re-up session/client when calling build/update/destroy

SERVICE = 's3'

# bucket

class bucket(resource):


    def __init__(self, session, name='', attributes={}, resource_template={}, live_data={}, plugins={}, verbose=False):
        super().__init__(
            session,
            SERVICE,
            name=name, 
            attributes=attributes, 
            resource_template=resource_template, 
            live_data=live_data,
            verbose=verbose
        )
        # self.__name = name
        # self.__resource_template = resource_template
        # self.__attributes = attributes
        # self.__live_data = live_data if live_data else self.__init_live_data()
        # self.__client = session.client(SERVICE)
        # self.__verbose = verbose

        # self.__actions = {
        #     'build': self.__init_build_actions(),
        #     'update': self.__init_update_actions(),
        #     'destroy': self.__init_destroy_actions()
        # }

        # self.__plugins = {
        #     'build': {
        #         'pre' : [],
        #         'post': []
        #     },
        #     'update': {
        #         'pre' : [],
        #         'post': []
        #     },
        #     'destroy': {
        #         'pre' : [],
        #         'post': []
        #     }
        # }

    
    # standard functions that should be roughly the same for all types of resources.
    # def build(self, attributes={}, resource_template={}, session=None):
    #     """executes build actions 1 by 1 and marks them as done.  raise error if dependencies found"""
    #     # if already exists, skip
    #     if self.__live_data:
    #         if self.__verbose:
    #             print('-skipping', self.__name) 
    #     else:
    #         if self.__verbose:
    #             print('-creating', self.__name)

    #     # if given an updated template, client, replace existing
    #     if resource_template:
    #         self.__resource_template = resource_template 
    #     if attributes:
    #         self.__attributes = attributes 
    #     if session:
    #         self.__client = session.client(SERVICE)

    #     for action in self.__actions['build']:
    #         if not action['complete']:
    #             function, arg_names = action['execution']

    #             args = dict_select(self.__attributes, arg_names)
                
    #             dependency(args) # raises error if dependencies found

    #             self.__live_data = { **self.__live_data, **function(**args) }

    #             action['complete'] = True

    #             yield self.live_data()
    

    # def update(self, attributes={}, resource_template={}, session=None):
    #     """executes update actions 1 by 1 and marks them as done.  raise error if dependencies found"""
    #     # TODO: only return actions that have the needed attributes 
    #     print(self.__actions['update'])
    #     for action in self.__actions['update']:
    #         print(action)
    #         if not action['complete']:
    #             function, arg_names = action['execution']

    #             args = dict_select(self.__attributes, arg_names)
                
    #             dependency(args) # raises error if dependencies found

    #             self.__live_data = { **self.__live_data, **function(**args) }

    #             action['complete'] = True

    #             yield self.live_data()


    # def destroy(self, attributes={}, session=None):
    #     """executes destroy actions 1 by 1 and marks them as done.  raise error if dependencies found"""
    #     for action in self.__actions['destroy']:
    #         if not action['complete']:
    #             function, arg_names = action['execution']

    #             function()
                
    #             self.__live_data = self.__init_live_data()

    #             action['complete'] = True

    #             yield self.live_data()


    def init_build_actions(self):
        """processes the saved resource template and returns build actions, args"""
        return [
            {
                'execution': ( self.__create_bucket, ['bucket'] ),
                'complete': False
            }
        ]


    def init_update_actions(self):
        """processes the saved resource template and returns update actions, args"""
        if self.verbose:
            print('-updating', self.name)
        actions = []
        
        # if safe_dict_val(self.__resource_template, 'update_mode', default='default'):
        #     actions = self.__init_destroy_actions() + self.__init_build_actions()

        actions += [
            {
                'execution': ( self.__configure_website, ['bucket', 'website_config'] ),
                'complete': False
            }
        ]
        
        return actions


    def init_destroy_actions(self):
        """processes the saved resource data and returns destroy actions, args"""
        return [
            {
                'execution': ( self.__delete_bucket, []),
                'complete': False
            }
        ]


    def init_live_data(self):
        return {}


    # def init_plugin(self, plugin_details, opts={}, pre=[], post=[]):
    #     self.__attributes = { **self.__attributes, **opts }
    #     self.__resource_template['attributes'] = { **self.__resource_template['attributes'], **opts }


    #     # TODO: instead of sort every time, maybe insert by priority?
    #     for stage in pre:
    #         self.__plugins[stage]['pre'] = sorted( self.__plugins[stage]['pre'] + [plugin_details], key=lambda x: x['priority'] )

    #     for stage in post:
    #         self.__plugins[stage]['post'] = sorted( self.__plugins[stage]['post'] + [plugin_details], key=lambda x: x['priority'] )


    # standard accessors
    # def live_data(self):
    #     return {
    #         self.__name : self.__live_data
    #     }

    
    # def name(self):
    #     return self.__name


    # def template(self):
    #     return self.__resource_template


    # def actions(self, key):
    #     return self.__plugins[key]['pre'] + self.__actions[key] + self.__plugins[key]['post']


    # def attributes(self):
    #     return self.__attributes


    # custom method for finding orphaned resources
    @classmethod
    def list_resources(cls, session=None):
        """yields a generator of all resources of this type that exist in the aws account"""
        client = session.client(SERVICE)

        buckets = client.list_buckets()['Buckets']

        for bucket in buckets:
            yield cls(
                session,
                name=bucket['Name'],
                live_data={
                    'name': bucket['Name'],
                    'region': '',
                    'arn': 'arn:aws:s3:::{}'.format(bucket['Name'])
                }
            )

    # custom functions to be called in build, update, destroy
    def __create_bucket(self, bucket):
        if self.live_data:
            if self.verbose:
                print('-skipping', bucket) 
            return self.live_data
        else:
            if self.verbose:
                print('-creating', bucket)
            response = self.client.create_bucket(
                Bucket=bucket
            )

        return { # TODO: come up with a way to template-ize this?
            'name': bucket,
            'region': response['Location'],
            'arn': 'arn:aws:s3:::{}'.format(bucket)
        }
    

    def __configure_website(self, bucket, website_config):
        """
            "website_config": {
                    "index": --> WebsiteConfiguration["IndexDocument"]["Suffix"],
                    "error": --> WebsiteConfiguration["ErrorDocument"]["Suffix"],
                    "redirect": {
                        "hostname": --> WebsiteConfiguration["RedirectAllRequestsTo"]["HostName"]
                        "https": True|False --> WebsiteConfiguration["RedirectAllRequestsTo"]["Protocol"]
                    },
                    "routing": --> not sure how to handle this
                }
        """

        if self.verbose:
            print('-configuring website for', self.name)

        args = {
            'IndexDocument': {
                'Suffix': website_config['index']  # this is the only mandatory parameter
            }
        }   
        
        # TODO: go through other possible args and add int args if they exist

        response = self.client.put_bucket_website(
            Bucket=bucket,
            WebsiteConfiguration=args
            )

        # TODO: get region?
        return {
            'website': 'http://{}.s3-website-us-east-1.amazonaws.com'.format(bucket)#self.__live_data["name"])
        }


    def __delete_bucket(self):
        # response = self.__client.delete_bucket(
        #     Bucket=self.__live_data['name']
        # )
        try:
            response = self.client.delete_bucket(
                Bucket=self.live_data['name']
            )
        except self.__client.exceptions.ClientError as e:
            if 'BucketNotEmpty' in str(e):
                raise DependecyNotMetError('An error occurred (BucketNotEmpty) when calling the DeleteBucket operation: The bucket you tried to delete is not empty') from e
            raise e

        # TODO: if bucketnotempty err, raise DependecyNotMetError()
        
        return {}

# object

class object(resource):


    def __init__(self, session, name='', attributes={}, resource_template={}, live_data={}, verbose=False):
        super().__init__(
            session,
            SERVICE,
            name=name, 
            attributes=attributes, 
            resource_template=resource_template, 
            live_data=live_data,
            verbose=verbose
        )
        # self.__name = name
        # self.__resource_template = resource_template
        # self.__attributes = attributes
        # self.__live_data = live_data if live_data else self.__init_live_data()
        # self.__client = session.client(SERVICE)
        # self.__verbose = verbose

        # self.__actions = {
        #     'build': self.__init_build_actions(),
        #     'update': self.__init_update_actions(),
        #     'destroy': self.__init_destroy_actions()
        # }

        # self.__plugins = {
        #     'build': {
        #         'pre' : [],
        #         'post': []
        #     },
        #     'update': {
        #         'pre' : [],
        #         'post': []
        #     },
        #     'destroy': {
        #         'pre' : [],
        #         'post': []
        #     }
        # }

    
    # standard functions that should be roughly the same for all types of resources.
    # def build(self, attributes={}, resource_template={}, session=None):
    #     """executes build actions 1 by 1 and marks them as done.  raise error if dependencies found"""
    #     # if already exists, skip
    #     if self.live_data:
    #         if self.verbose:
    #             print('-skipping', self.name) 
    #     else:
    #         if self.verbose:
    #             print('-creating', self.name)

    #     # if given an updated template, client, replace existing
    #     if resource_template:
    #         self.resource_template = resource_template 
    #     if attributes:
    #         self.attributes = attributes 
    #     if session:
    #         self.client = session.client(SERVICE)

    #     for action in self.actions('build'):
    #         if not action['complete']:
    #             function, arg_names = action['execution']

    #             args = dict_select(self.attributes, arg_names)
                
    #             dependency(args) # raises error if dependencies found

    #             self.live_data = { **self.live_data, **function(**args) }

    #             action['complete'] = True

    #             yield self.live_resource_data()
    

    # def update(self, attributes={}, resource_template={}, session=None):
    #     """executes update actions 1 by 1 and marks them as done.  raise error if dependencies found"""
    #     # TODO: only return actions that have the needed attributes 
    #     for action in self.actions('update'):
    #         if not action['complete']:
    #             function, arg_names = action['execution']

    #             args = dict_select(self.attributes, arg_names)
                
    #             dependency(args) # raises error if dependencies found

    #             self.live_data = { **self.live_data, **function(**args) }

    #             action['complete'] = True

    #             yield self.live_resource_data()


    # def destroy(self, attributes={}, session=None):
    #     """executes destroy actions 1 by 1 and marks them as done.  raise error if dependencies found"""
    #     for action in self.actions('destroy'):
    #         if not action['complete']:
    #             function, arg_names = action['execution']
                
    #             function()

    #             self.live_data = self.init_live_data()

    #             action['complete'] = True

    #             yield self.live_resource_data()


    def init_build_actions(self):
        """processes the saved resource template and returns build actions, args"""
        return [
            {
                'execution': ( self.__put_objects, ['bucket', 'source', 'prefix'] ), 
                'complete': False
            }
        ]


    def init_update_actions(self):
        """processes the saved resource template and returns update actions, args"""
        return [
            {
                'execution': ( self.__put_objects, ['bucket', 'source', 'prefix'] ), 
                'complete': False
            },
            {
                'execution': ( self.__put_object_acl, ['bucket', 'acls'] ),
                'complete': False
            }
        ]


    def init_destroy_actions(self):
        """processes the saved resource data and returns destroy actions, args"""
        return [
            {
                'execution': ( self.__delete_objects, [] ),
                'complete': False
            }
        ]


    def init_live_data(self):
        return {
            'bucket': '',
            'keys': []
        }


    # def init_plugin(self, plugin_details, opts={}, pre=[], post=[]):
    #     self.attributes = { **self.attributes, **opts }
    #     self.resource_template['attributes'] = { **self.resource_template['attributes'], **opts }

    #     for stage in pre:
    #         self.plugins[stage]['pre'] = sorted( self.plugins[stage]['pre'] + [plugin_details], key=lambda x: x['priority'] )

    #     for stage in post:
    #         self.plugins[stage]['post'] = sorted( self.plugins[stage]['post'] + [plugin_details], key=lambda x: x['priority'] )


    # def actions(self, key):
    #     return self.plugins[key]['pre'] + self.actions[key] + self.plugins[key]['post']


    # standard accessors
    # def live_data(self):
    #     return {
    #         self.name : self.live_data
    #     }

    
    # def name(self):
    #     return self.name


    # def template(self):
    #     return self.resource_template


    # def attributes(self):
    #     return self.attributes


    # custom method for finding orphaned resources
    @classmethod
    def list_resources(cls, session=None):
        """yields a generator of all resources of this type that exist in the aws account"""
        client = session.client(SERVICE)

        buckets = client.list_buckets()['Buckets']

        for bucket in buckets:
            bucket_objects = response = client.list_objects( # TODO: will we have pagination issues?
                Bucket='string'
            )['Contents']
            yield cls(
                session,
                name='{}_objects'.format(bucket['Name']),
                live_data={
                    'bucket': bucket['Name'],
                    'region': '', # TODO: region
                    'keys': [ obj['Key'] for obj in bucket_objects ]
                }
            )


    # custom functions to be called in build, update, destroy
    def __put_objects(self, bucket, source, prefix):

        self.live_data['bucket'] = bucket #TODO should this be handled elsewhere?

        # iterate over list of files in source path
        source_paths = [source] 
        if(source[-1] == '/'):  # if source is a dir, the overwrite
            source_paths = list(list_dir(source))

        for path in source_paths:
            key = "{prefix}/{suffix}".format(prefix=prefix, suffix=path.split(source, 1)[-1]) if prefix else path.split(source, 1)[-1]
            
            ############## TEMPORARY FIX ##############
            metadata_lookup = {
                'js': 'application/javascript',
                'html': 'text/html',
                'css': 'text/css',
                'png': 'image/png',
                'gz': 'application/javascript'
            }
            ###########################################

            if key in self.live_data['keys']: # TODO: get rid of these checks, should just be in "build" function
                if self.verbose:
                    print('-skipping', key) 
            else:
                if self.verbose:
                    print('-creating', key)
                try: # TODO: come with some standard boto try except that handles expected boto errors?
                    response = self.client.put_object(
                        Bucket=bucket,
                        Body=file_obj(path),
                        Key=key,
                        ContentType=metadata_lookup[key.split('.')[-1]]
                    )
                    self.live_data['keys'].append(key)
                except Exception as e:
                    print(e)

        return self.live_data # TODO this feels weird... should these just update live_data as they go and return nothing?


    def __put_object_acl(self, bucket, acls):
        """
            "acls": {
                "read": ["ALL"]
            },
        """

        grants = {
            'full_control': 'GrantFullControl',
            'read': 'GrantRead',
            'read_acp': 'GrantReadACP',
            'write': 'GrantWrite',
            'write_acp': 'GrantWriteACP',
        }


        args = {}

        for access_type in acls.keys():
            if grants[access_type] not in args.keys():
                args[grants[access_type]] = ''
            if "ALL" in acls[access_type]:
                args[grants[access_type]] = 'uri=http://acs.amazonaws.com/groups/global/AllUsers'
            # TODO: handle if they give you more accessthingies

        #policies = attr['policies']
        for key in self.live_data['keys']:
            response = self.client.put_object_acl(
                **args,
                Bucket=bucket,
                Key=key
            )

        return {} # Nothing new to return


    def __delete_objects(self):
        for key in self.live_data['keys']:
            response = self.client.delete_object(
                Bucket=self.live_data['bucket'],
                Key=key
            )

        return {}

