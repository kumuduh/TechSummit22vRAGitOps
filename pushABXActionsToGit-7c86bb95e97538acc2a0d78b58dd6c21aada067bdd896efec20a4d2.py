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
    
def getABX(baseurl,access_token,apiVersion):
    headers = {"Authorization":access_token}
    uri_filter_abx = urllib.parse.quote(f"system eq false")
    abx_uri = f'/abx/api/resources/actions?apiVersion={apiVersion}&$filter={uri_filter_abx}&page=0'
    print(f'Get ABX uri {abx_uri}')
    abx_respose = requests.get(f'{baseurl}{abx_uri}',headers = headers, verify=False)
    if abx_respose.status_code != 200:
        print(f'Failed to getvRA ABX')
    else:    
        abx_Obj = abx_respose.json()['content'] 
        if int(abx_respose.json()['totalPages']) > 1:
            for page in range(1,abx_respose.json()['totalPages']):
                abx_uri = f'/abx/api/resources/actions?apiVersion={apiVersion}&$filter={uri_filter_abx}&page={page}'
                abx_respose = requests.get(f'{baseurl}{abx_uri}',headers = headers, verify=False)
                abx_Obj = abx_Obj + abx_respose.json()['content']    
    #print(f'Get ABX is successful. ABX Actions {abx_Obj}')        
    return abx_Obj
    
def push(repo, path, message, content, branch, update=False):
    print(f'Pushing to github {path} with update {update}')

    if update:  # If file already exists, update it
        contents = repo.get_contents(path, ref="main")  # Retrieve old file to get its SHA and path
        repo.update_file(contents.path, message, content, contents.sha, branch=branch)  # Add, commit and push branch
    else:  # If file doesn't exist, create it
        repo.create_file(path, message, content, branch=branch)  # Add, commit and push branch


def handler(context, inputs):
    
    print('Executing Push vRA ABX Actions to Git...')
    
    #Get inputs
    apiVersion = inputs['apiVersion']
    baseurl = inputs['vraBaseUrl']
    refToken = inputs['vraAPIToken']
    headers = {"Accept":"application/json","Content-Type":"application/json"}
    access_token = getToken(baseurl,refToken,headers)

    #gitlab_token = context.getSecret(inputs["gitLabToken"])
    github_token = inputs["gitHubToken"]
    #print(f'GitLab Token: {github_token}')
    git_repo = inputs['gitRepo']
    create_mr = inputs['createMergeRequest']
    
    g = Github(github_token)
    repo = g.get_repo(git_repo)
    
    #git_project = gl.projects.get(git_project_id)
    print(f'Git Repo {repo.name} \n')
    
    try:
        repo_abx = repo.get_contents('actions','main')     
        gitACName = extract_values(repo_abx,'path')
        print(f'Git Repo actions path: {repo_abx} \n')
        #print(f'Git Repo actions path names: {gitACName} \n')
    except UnknownObjectException:
        print(f'Initial repo. adding read.me')
        repo_abx = []

    #Get ABX actions
    abx_Obj = getABX(baseurl,access_token,apiVersion)
    #print(f'vRA Actions: {abx_Obj}')
    active_abx_objs = []    
    commit_actions = []

    dt = datetime.now()
    branch_name = 'vra-ABXActions-' + dt.strftime('%Y%m%d-%H-%M-%S')
    # Create new branch from main    
    source = repo.get_branch("main")
    repo.create_git_ref(ref=f"refs/heads/{branch_name}", sha=source.commit.sha)     

    for ac in abx_Obj:
        active_abx_objs.append(ac)
        ac_filename = f'{ac["name"]}.json'
        file_path = f'actions/{ac_filename}'
        print(f'ABX file path in repo {file_path}')
        #Check If actions already in the repo
        matching_abx = next((item for item in repo_abx if (item.name == ac_filename)), False)
        if matching_abx:
            print(f"adding new version of ABX: {file_path}")
            push(repo, file_path, f"vRA ABX Commit for {ac['name']}", json.dumps(ac), branch_name, update=True)
        else:
            print(f"adding new Actions {file_path}")
            push(repo, file_path, f"vRA ABX Commit for {ac['name']}", json.dumps(ac), branch_name, update=False)
    
    

    # Create Pull Request
    if create_mr.lower() == 'true':    
        pr_title = f'vRA ABX Actions realease {dt.strftime("%Y:%m:%d")}'
        print(f'Creating Pull request with title: {pr_title}')
        pr = repo.create_pull(title=pr_title, body=pr_title, head=branch_name, base="main")
        #pr.edit(state="closed")
    
    #set outputs
    abx_out = extract_values(active_abx_objs,'name')
 
    
    out_puts = {
        'abx': abx_out
    }
    
    return out_puts