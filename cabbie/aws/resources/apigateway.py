# TODO: maybe rename? we called this lmbda to avoid conflict with lambda reserved word

from .resources import resource
from .resources import DependecyNotMetError

from time import sleep


SERVICE = 'apigateway'

# function

class rest_api(resource):


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


    def init_build_actions(self):
        """processes the saved resource template and returns build actions, args"""
        return [
            {
                'execution': ( self.__create_api, ['name', 'model'] ),
                'complete': False
            }
        ]


    def init_update_actions(self):
        """processes the saved resource template and returns update actions, args"""
        actions = [
            {
                'execution': ( self.__update_code, ['name', 'code', 'publish']),
                'complete': False
            },
            {
                'execution': ( self.__update_config, ['name', 'role', 'runtime', 'handler', 'timeout', 'memory', 'environment_variables']),
                'complete': False
            },
            {
                'execution': ( self.__add_permissions, ['name', 'permissions']),
                'complete': False
            }
        ]
        
        # if safe_dict_val(self.__resource_template, 'update_mode', default='default'):
        #     actions = self.__init_destroy_actions() + self.__init_build_actions()

        actions += []
        
        return actions


    def init_destroy_actions(self):
        """processes the saved resource data and returns destroy actions, args"""
        return [
            {
                'execution': ( self.__delete_function, []),
                'complete': False
            }
        ]


    def init_live_data(self):
        return {
            'name': ''
        }


    # custom method for finding orphaned resources
    @classmethod
    def list_resources(cls, session=None):
        """yields a generator of all resources of this type that exist in the aws account"""
        client = session.client(SERVICE)

        policies = client.list_policies(
            Scope='Local',
            MaxItems=1000 # TODO: paginate?
        )['Policies'] # we only care about customer managed policies

        for policy in policies:
            yield cls(
                session,
                name=policy['PolicyName'],
                live_data={
                    'name': policy['PolicyName'],
                    'arn': policy['Arn']
                }
            )

    # custom functions to be called in build, update, destroy
    def __create_api(self, name, model):
        # TODO: make publish, timeout, memorysize optional

        if model == 'default':
            args = {
                'name': name
            }

            response = self.client.create_rest_api(**args) # TODO: if we get an error about the IAM role, raise dependency error
        elif model == 'import':
            # TODO: let users import from swagger, etc
            raise Exception('Not Implemented')
        #return self.live_data

        # we need to get the resource ID for '/' path
        retries = 1
        wait_time = 1

        while retries < 5:
            try:
                root_resource_response = self.client.get_resources(
                    restApiId=response['id']
                )

                retries = 9
            except:
                sleep(wait_time)
                retries += 1
                wait_time *= 2

        if retries == 5:
            raise Exception("Too many retries, failed to create {}".format(self.name))
        

        return {
            'id': response['id'],
            'name': response['name'],
            '/': root_resource_response['items'][0] 
        }

    
    def __deploy_api(self):
        pass

    
    def __update_config(self, name, role, runtime, handler, timeout, memory, environment_variables):
        args = {
            'FunctionName': name,
            'Role': role,
            'Handler': handler,
            'Timeout': timeout,
            'MemorySize': memory,
            'Environment': {
                'Variables': environment_variables
            },
            'Runtime': runtime
        }

        response = self.client.update_function_configuration(**args)

        #return self.live_data

        return {
            'aws_managed': True if response else False,
            'name': response['FunctionName'],
            'arn': response['FunctionArn']
        }

    
    def __update_code(self, name, code, publish):

        args = {
            'FunctionName': name,
            'ZipFile': code,
            'Publish': publish
        }

        response = self.client.update_function_code(**args)

        #return self.live_data

        return {}

    
    def __add_permissions(self, name, permissions):

        for permission in permissions:
            args = {
                'FunctionName': name,
                'StatementId': permission['sid'], #TODO should we automate this?  do i need to make people provide this?  i feel like ideally cabbie shoul dknow if identical positions already exist and then add or not based on that, not an SID
                'Action': permission['action'],
                'Principal': permission['principal'],
                'SourceArn': permission['source_arn'],
            }

            response = self.client.add_permission(**args)

        #return self.live_data

        return { }


    def __delete_function(self):
        # response = self.__client.delete_bucket(
        #     Bucket=self.__live_data['name']
        # )
        response = self.client.delete_function(
            FunctionName=self.live_data['name']
        )

        # TODO: if bucketnotempty err, raise DependecyNotMetError()
        
        return {}