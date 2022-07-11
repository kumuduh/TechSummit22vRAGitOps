import json
import urllib.parse
import requests
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
        bearer = "Bearer " + req.json()["token"]
        #print(f'bearer token {bearer}')
    return bearer
    
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

def getBPs(baseurl,access_token,apiVersion,prj_name):
    headers = {"Authorization":access_token}
    uri_filter_bp = urllib.parse.quote(f"projectName eq '{prj_name}'")
    bp_uri = f'/blueprint/api/blueprints?apiVersion={apiVersion}&$filter={uri_filter_bp}&page=0'
    print(f'Get BP uri {bp_uri}')
    bp_respose = requests.get(f'{baseurl}{bp_uri}',headers = headers, verify=False)
    if bp_respose.status_code >= 400:
        print(f'Failed to getvRA BPs')
        bp_respose.raise_for_status()
    else:    
        bp_Obj = bp_respose.json()['content'] 
        if int(bp_respose.json()['totalPages']) > 1:
            for page in range(1,bp_respose.json()['totalPages']):
                bp_uri = f'/blueprint/api/blueprints?apiVersion={apiVersion}&$filter={uri_filter_bp}&page={page}'
                bp_respose = requests.get(f'{baseurl}{bp_uri}',headers = headers, verify=False)
                bp_Obj = bp_Obj.append(bp_respose.json()['content'])


    #print(f'Get BP is successful. BPs {bp_Obj}')        
    return bp_Obj
    
def create_update_cloud_templates(baseurl,access_token,apiVersion,method,payload,bp_id):
    headers = {"Authorization":access_token}
    #print(f"BP Action CRUD payload:\n {palyload}")
    
    if (method == 'PUT'):
        bp_uri = f'/blueprint/api/blueprints/{bp_id}?apiVersion={apiVersion}'
        print(f'url {bp_uri}')
        bp_resp_obj = requests.put(f'{baseurl}{bp_uri}', headers = headers, verify = False, json = payload)
    else:
        bp_uri = f'/blueprint/api/blueprints?apiVersion={apiVersion}'
        print(f'url {bp_uri}')
        bp_resp_obj = requests.post(f'{baseurl}{bp_uri}', headers = headers, verify = False, json = payload)
        
    if bp_resp_obj.status_code > 400:
        #raise Exception (f'Failed CRUD BP Action. Error code {bp_resp_obj.status_code}')
        print(f'Failed CRUD BP Action. Error code {bp_resp_obj.status_code}')
        bp_resp_obj.raise_for_status()
    else:
        print(f'vRA BP create_update ACTION CRUD successful ') 
        bp_out_obj = bp_resp_obj.json()
        
    #print(f'vRA BP  retured after CRUD: \n {bp_out_obj}')
    return bp_out_obj     

def handler(context, inputs):
    
    print('Executing Deploy vRA project Cloud Templates...')
    
    #Get inputs
    apiVersion = inputs['apiVersion']
    baseurl = inputs['vraBaseUrl']
    refToken = inputs['vraAPIToken'] 
    project_name = inputs['projectName']
    release_version = inputs['releaseVersion']

    #Get vRA access token
    headers = {"Accept":"application/json","Content-Type":"application/json"}
    access_token = getToken(baseurl,refToken,headers)
    
    #gitlab_token = context.getSecret(inputs["gitLabToken"])
    github_token = inputs["gitHubToken"]
    #print(f'GitLab Token: {github_token}')
    git_repo = inputs['gitRepo']
    git_branch = inputs['gitBranch']
    
    #git access
    g = Github(github_token)
    repo = g.get_repo(git_repo)
    
    #git_project = gl.projects.get(git_project_id)
    print(f'Git Repo {repo.name} \n')
    
    try:
        repo_blueprints = repo.get_contents('blueprints',git_branch)     
        print(f'Git Repo blueprints path: {repo_blueprints} \n')
    except UnknownObjectException:
        print(f'Initial repo.')
        repo_blueprints = []   
    
    #Get project info
    prj_obj = getProject(baseurl,access_token,apiVersion,project_name)
    prj_id = prj_obj['id']
    org_id = prj_obj['orgId']
    
    #Get Blueprint 
    project_bp_obj = getBPs(baseurl,access_token,apiVersion,project_name)
    project_bp_ids = extract_values(project_bp_obj,'id')
    project_bp_names = extract_values(project_bp_obj,'name')
    bp_out = []

    for bp_dir in repo_blueprints:
        #print(bp)
        if (bp_dir.type == "dir"):
            #print(f'BP folder: {bp_dir.path}')
            #print(f'BP folder name: {bp_dir.name}')
            bp_file = repo.get_contents(bp_dir.path,git_branch)
            if (bp_file[0].path.endswith('.yaml')):
                #should always bluprint.yaml only
                print(f'BP yaml file path: {bp_file[0].path}')
                bp_yaml = repo.get_contents(bp_file[0].path,git_branch).decoded_content.decode("utf-8")
                #print(f'Blueprint YAML: {bp_yaml}')
                bp_obj = {
                    "content": bp_yaml,
                    "description": f'{bp_dir.name} synced from Git Repo',
                    "name": bp_dir.name,
                    "projectId": prj_id,
                    "requestScopeOrg": True
                }
                matching_blueprint = False
                bp_id = None
                for prj_bp in project_bp_obj:
                    if (prj_bp['name'].upper() == bp_dir.name.upper()):
                        print(f'Found matching BP: {prj_bp["name"]}')
                        matching_blueprint = True
                        bp_id = prj_bp['id']
                        break
                    
                #TODO: Remove if for test Kumudu bp      
                if matching_blueprint:
                    print(f'Cloud Template: {bp_dir.name} is alreay in vRA. Update with new version')
                    if(bp_dir.name == "test Kumudu"):
                        print('Found test bp in vRA. update')
                        vRA_bp_obj = create_update_cloud_templates(baseurl,access_token,apiVersion,'PUT',bp_obj,bp_id)
                else:
                    print(f'New Cloud Template {bp_dir.name}')
                    if(bp_dir.name == "test Kumudu"):
                        print('NOT Found test bp in vRA. create')            
                        vRA_bp_obj = create_update_cloud_templates(baseurl,access_token,apiVersion,'POST',bp_obj,bp_id)
                        
                if(bp_dir.name == "test Kumudu"):        
                    print(f'Updated BP id : {vRA_bp_obj["id"]}')
       
                    #Set BP version,
                    #print(f'Updated BP id : {vRA_bp_obj["id"]}')
                    bp_version_obj = {
                        "changeLog": f"Cloud Template {bp_dir.name} release {release_version}",
                        "description": f"Cloud Template {bp_dir.name} release {release_version}",
                        "release": False,
                        "version": release_version
                    }
                    bp_version_resp_obj = requests.post(url = f'{baseurl}/blueprint/api/blueprints/{vRA_bp_obj["id"]}/versions?apiVersion={apiVersion}', headers = {'Authorization': access_token}, json = bp_version_obj, verify = False)
                    print(f'BP new Version: {bp_version_resp_obj} ')
                    bp_out.append(bp_dir.name)
    
    
    #set outputs

    out_puts = {
        'deployed_blueprints': bp_out
    }
    
    return out_puts