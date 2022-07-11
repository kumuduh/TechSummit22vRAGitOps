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
    #print(resp['content'])
    #print(resp['headers'])        
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
    else:
        print('Successfully login to CAS!!') 
        bearer = "Bearer " + req.json()["token"]
        #print(f'bearer token {bearer}')
    return bearer

def createSubscription(baseurl,access_token,apiVersion,sub_payload):
    headers = {'Content-Type': 'application/json','Accept': 'application/json','Authorization':access_token}
    sub_uri = f'/event-broker/api/subscriptions?apiVersion={apiVersion}'
    print(f'Create EBS uri {sub_uri}')
    print(f'EBS payload:\n {sub_payload}')
    sub_respose = requests.post(f'{baseurl}{sub_uri}', json=sub_payload, headers = headers, verify=False)
    print(f'Create EBS response : {sub_respose}')
    if sub_respose.status_code > 400:
        print(f'Failed to create vRA EBS!!')
    else:    
        print(f'Successfully created vRA EBS')
    

def handler(context, inputs):
    
    print('Executing Deploy vRA Subscriptions...')
    
    #Get inputs
    apiVersion = inputs['apiVersion']
    baseurl = inputs['vraBaseUrl']
    refToken = inputs['vraAPIToken']    
    project_name = inputs['projectName']
    release_version = inputs['releaseVersion']

    github_token = inputs["gitHubToken"]
    git_repo = inputs['gitRepo']
    git_branch = inputs['gitBranch']

    #Get vRA access token
    headers = {"Accept":"application/json","Content-Type":"application/json"}
    access_token = getToken(baseurl,refToken,headers)
    
    #git access
    g = Github(github_token)
    repo = g.get_repo(git_repo)

    print(f'Git Repo {repo.name} \n')
    
    try:
        repo_subs = repo.get_contents('subscriptions',git_branch)     
        print(f'Git Repo subscriptions path: {repo_subs} \n')
    except UnknownObjectException:
        print(f'Initial repo.')
        repo_subs = []  

    subs_out = []

    for sub_dir in repo_subs:
        #print(sub_dir)
        sub_file = repo.get_contents(sub_dir.path,git_branch)
        #should always sub.json & read.me 
        print(f'Form json file path: {sub_file.path}')
        if (sub_file.path.endswith('.json')):

            sub_raw = repo.get_contents(sub_dir.path,git_branch).decoded_content.decode("utf-8")
            #sub_raw =  repo.get_contents(sub_dir.path,git_branch).decoded_content
            print(f'EBS RAW file content from Git:\n {sub_raw}')
            sub_json = json.loads(sub_raw)
            
            print(f'EBS JSON content :\n {sub_json["name"]}')
            
            #TODO: UPdate Subs for Destination env. i.e conditions, project scope ... etc. 
            sub_json['description'] = f"{sub_json['name']} release: {release_version} "
            createSubscription(baseurl,access_token,apiVersion,sub_json)
            subs_out.append(sub_json['name'])
        else:
            print(f'SKIP none json files {sub_file.path}')
    
    #set outputs
    out_puts = {
        'deployed_subscriptions': subs_out
    }
    
    return out_puts