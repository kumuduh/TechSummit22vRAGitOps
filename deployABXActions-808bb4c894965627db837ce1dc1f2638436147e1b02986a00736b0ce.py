import json
import urllib.parse
import requests
#import gitlab
#import git
from datetime import datetime
from github import Github, GithubException, UnknownObjectException


def vRAC_RESTCall(ctx,method,uri,palyload):
    print(f'vRA REST call uri - {uri} method - {method} ')
    cas_headers = {"Content-Type":"application/json","Accept":"application/json"}
    resp = ctx.request(uri, method, palyload, headers=cas_headers)
    
    json_resp = {}
    try:
        json_resp = json.loads(resp['content'])
    except json.decoder.JSONDecodeError as ex:
        print("Error occured while parsing json response: ")
        print(ex)
    print('vRA API via proxy call executed.')      
    return json_resp
    
def extract_values(obj, key):
    """Pull all values of specified key from nested JSON."""
    arr = []
    def extract(obj, arr, key):
        """Recursively search for values of key in JSON tree."""
        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(v, (dict, list)):
                    extract(v, arr, key)
                elif k == key:
                    arr.append(v)
        elif isinstance(obj, list):
            for item in obj:
                extract(item, arr, key)
        return arr
    results = extract(obj, arr, key)
    return results
    
def getToken(baseurl,refToken,headers):
    payload = {"refreshToken": refToken}
    print(f'Payload for login into vRAC {payload}')
    uri = "/iaas/api/login"
    req = requests.post(f'{baseurl}{uri}', json=payload, headers = headers, verify=False)
    bearer = ""
    if req.status_code != 200:
        print(f'Unsuccessful Login Attmept. Error code {req.status_code}')
        req.raise_for_status()
    else:
        print('Successfully login to CAS!!') 
        ###bearer = "Bearer "
        bearer = "Bearer " + req.json()["token"]
        #print(f'bearer token {bearer}')
    return bearer
    
def getABX(baseurl,access_token,apiVersion):
    headers = {"Authorization":access_token}
    uri_filter_abx = urllib.parse.quote(f"system eq false")
    abx_uri = f'/abx/api/resources/actions?apiVersion={apiVersion}&$filter={uri_filter_abx}&page=0'
    print(f'Get ABX uri {abx_uri}')
    abx_respose = requests.get(f'{baseurl}{abx_uri}',headers = headers, verify=False)
    if abx_respose.status_code >= 400:
        print(f'Failed to get vRA ABX')
        abx_respose.raise_for_status()
    else:    
        abx_Obj = abx_respose.json()['content'] 
        if int(abx_respose.json()['totalPages']) > 1:
            for page in range(1,abx_respose.json()['totalPages']):
                abx_uri = f'/abx/api/resources/actions?apiVersion={apiVersion}&page={page}'
                abx_respose = requests.get(f'{baseurl}{abx_uri}',headers = headers, verify=False)
                abx_Obj = abx_Obj + abx_respose.json()['content']    


    #print(f'Get ABX is successful. ABX Actions {abx_Obj}')        
    return abx_Obj
    
def getProject(baseurl,access_token,apiVersion,prj_name):
    headers = {"Authorization":access_token}
    uri_filter_prj = urllib.parse.quote(f"name eq '{prj_name}'")
    prj_uri = f'/iaas/api/projects?apiVersion={apiVersion}&$filter={uri_filter_prj}'
    print(f'Get Project uri {prj_uri}')
    prj_response = requests.get(f'{baseurl}{prj_uri}', headers = headers, verify=False)
    prj_obj = {}
    if prj_response.status_code >= 400:
        print(f'Failed get vRA Project {prj_name}. Error code {prj_response.status_code}')
        prj_response.raise_for_status()
    else:
        print(f'Get project {prj_name} successful ') 
        prj_obj = prj_response.json()["content"][0]
        #print(f'Project Obj {prj_obj}')
    return prj_obj   
    
def create_update_abx_action(baseurl,access_token,apiVersion,method,action_id,payload):
    headers = {"Authorization":access_token}
    print(f"ABX Action CRUD payload:\n {payload}")
    
    if (method == 'PUT'):
        ac_uri = f'/abx/api/resources/actions/{action_id}?apiVersion={apiVersion}'
        print(f'url {ac_uri}')
        ac_res_obj = requests.put(f'{baseurl}{ac_uri}', headers = headers, verify = False, json = payload)
    else:
        ac_uri = f'/abx/api/resources/actions?apiVersion={apiVersion}'
        print(f'url {ac_uri}')
        ac_res_obj = requests.post(f'{baseurl}{ac_uri}', headers = headers, verify = False, json = payload)
        
    if ac_res_obj.status_code > 400:
        #raise Exception (f'Failed CRUD ABX Action. Error code {ac_res_obj.status_code}')
        print(f'Failed CRUD ABX Action. Error code {ac_res_obj.status_code}')
        ac_res_obj.raise_for_status()
    else:
        print(f'ABX ACTION CRUD successful ') 
        ac_out_obj = ac_res_obj.json()
        
    #print(f'vRA ABX action retured after CRUD: \n {ac_out_obj}')
    return ac_out_obj  
    
def handler(context, inputs):
    
    print('Executing Deploy vRA ABX Actions...')
    # Assume All Actions are in same vRA project !! 
    
    #Get inputs
    apiVersion = inputs['apiVersion']
    baseurl = inputs['vraBaseUrl']
    refToken = inputs['vraAPIToken'] 
    project_name = inputs['projectName']
    release_version = inputs['releaseVersion']
    
    #Get vRA access token
    headers = {"Accept":"application/json","Content-Type":"application/json"}
    access_token = getToken(baseurl,refToken,headers)    
    
    github_token = inputs["gitHubToken"]
    git_repo = inputs['gitRepo']
    git_branch = inputs['gitBranch']
    
    #git access
    g = Github(github_token)
    repo = g.get_repo(git_repo)
    
    print(f'Git Repo {repo.name} \n')
    
    try:
        repo_abx = repo.get_contents('actions',git_branch)     
        print(f'Git Repo actions path: {repo_abx} \n')
    except UnknownObjectException:
        print(f'Initial repo.')
        repo_abx = []   
    #TODO: Possible to get commit id and use it as release_version
    
    #Get project info
    prj_obj = getProject(baseurl,access_token,apiVersion,project_name)
    prj_id = prj_obj['id']
    org_id = prj_obj['orgId']
    #Get Blueprint 
    #Get ABX actions
    abx_Objs = getABX(baseurl,access_token,apiVersion)
    #print(f'vRA Actions: {abx_Objs}')
    active_abx_objs = []  
    ac_out = []

    for abx_dir in repo_abx:
        #print(abx_dir)
        abx_file = repo.get_contents(abx_dir.path,git_branch)
        #should always abx.json & read.me 
        print(f'ABX Action json file path: {abx_file.path}')
        if (abx_file.path.endswith('.json')):
            action_raw = repo.get_contents(abx_file.path,git_branch).decoded_content.decode("utf-8")
            #print(f'Action RAW file content from Git:\n {action_raw}')
            action_json = json.loads(action_raw)
            org_ac_name = action_json["name"]
            print(f'ABX Action name: {org_ac_name}')
            #action_json['name'] = f"{org_ac_name}_{release_version}"
            action_json['projectId'] = prj_id
            action_json['orgId'] = org_id
            if 'description' in action_json:
                action_json['description'] = f'{action_json["description"]}\n - {release_version}'
            else:
                action_json['description'] = f'{org_ac_name} - {release_version}'
            
            #Modify before deploy to new vRA
            #remove old fields
            '''if 'id' in action_json:
                del action_json['id']
            if 'createdMillis' in action_json:
                del action_json['createdMillis']
            if 'updatedMillis' in action_json:
                del action_json['updatedMillis']
            if 'metadata' in action_json:
                del action_json['metadata']
            if 'cpuShares' in action_json:
                del action_json['cpuShares']
            if 'memoryInMB' in action_json:
                del action_json['memoryInMB']
            if 'timeoutSeconds' in action_json:
                del action_json['timeoutSeconds'] 
            if 'deploymentTimeoutSeconds' in action_json:
                del action_json['deploymentTimeoutSeconds']
            if 'provider' in action_json:
                del action_json['provider']
            if 'configuration' in action_json:
                del action_json['configuration']
            if 'system' in action_json:
                del action_json['system']                
            if 'scalable' in action_json:
                del action_json['scalable']
            if 'shared' in action_json:
                del action_json['shared']
            if 'asyncDeployed' in action_json:
                del action_json['asyncDeployed']
            if 'selfLink' in action_json:
                del action_json['selfLink']'''               
            #matching_blueprint = next((item for item in abx_Objs if (item["name"] == abx_dir.name)), False)
            matching_action = False
            ac_id = None
            for ac in abx_Objs:
                if (ac['name'].upper() == org_ac_name.upper()):
                    print(f'Found matching Action: {ac["name"]}')
                    matching_action = True
                    ac_id = ac['id']
                    break
                
            #Filter what you want to deploy i.e Remove/update if for hello.json     
            if matching_action:
                print(f'ABX Action : {abx_dir.name} is alreay in vRA. Update with new version')
                if(abx_dir.name == "hello.json"):
                    print('Found hello action in vRA. update')
                    vRA_ac_obj = create_update_abx_action(baseurl,access_token,apiVersion,'PUT',ac_id,action_json)
            else:
                print(f'Creating new ABX Action with name {abx_dir.name}')
                if(abx_dir.name == "hello.json"):
                    print('NOT Found hello.json in vRA. create new action')            
                    vRA_ac_obj = create_update_abx_action(baseurl,access_token,apiVersion,'POST','',action_json)
                    
            if(abx_dir.name == "hello.json"):        
                print(f'Updated Action version id : {vRA_ac_obj["id"]}')
       
                #Set ACtion version
                ac_version_obj = { 'name': release_version, 'released': True,'description': f'Release from git repo {git_repo} and branch {git_branch}' }
                
                ac_version_resp = requests.post(url = f'{baseurl}/abx/api/resources/actions/{vRA_ac_obj["id"]}/versions?apiVersion={apiVersion}&projectId={prj_id}', headers = {'Authorization': access_token}, json = ac_version_obj, verify = False)
                #print(f'Action new Version: {ac_version_resp} ')
                ac_out.append(abx_dir.name)
                ac_version_resp.raise_for_status()
    
    
    #set outputs
    out_puts = {
        'deployed_actions': ac_out
    }
    
    return out_puts