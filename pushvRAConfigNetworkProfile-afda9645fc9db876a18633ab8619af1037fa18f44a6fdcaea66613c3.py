import json
import urllib.parse
import requests
from datetime import datetime
#from github import Github
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
    
def getNetworkProfiles(baseurl,access_token,apiVersion):
    headers = {"Authorization":access_token}
    n_uri = f'/iaas/api/network-profiles?apiVersion={apiVersion}'
    print(f'Get Network profiles uri {n_uri}')
    n_respose = requests.get(f'{baseurl}{n_uri}',headers = headers, verify=False)
    if n_respose.status_code >= 400:
        print(f'Failed to getvRA Network Profiles')
        n_respose.raise_for_status()
    else:    
        n_Obj = n_respose.json()['content'] 

    #print(f'Get Network is successful. Zones {z_Obj}')        
    return n_Obj


def push(repo, path, message, content, branch, update=False):
    print(f'Pushing to github {path} with update {update}')

    if update:  # If file already exists, update it
        contents = repo.get_contents(path, ref="main")  # Retrieve old file to get its SHA and path
        repo.update_file(contents.path, message, content, contents.sha, branch=branch)  # Add, commit and push branch
    else:  # If file doesn't exist, create it
        repo.create_file(path, message, content, branch=branch)  # Add, commit and push branch


def handler(context, inputs):
    
    print('Executing Get vRA Image Profiles...')
    
    #Get inputs
    apiVersion = inputs['apiVersion']
    baseurl = inputs['vraBaseUrl']
    refToken = inputs['vraAPIToken']
    headers = {"Accept":"application/json","Content-Type":"application/json"}
    access_token = getToken(baseurl,refToken,headers)
    vra_site = inputs['vRASite']

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
        repo_config = repo.get_contents('vRAConfig','main')     
        #gitfrmName = extract_values(repo_config,'ContentFile')
        print(f'Git Repo Forms path: {repo_config} \n')
        #print(f'Git Repo Forms path names: {gitfrmName} \n')
    except UnknownObjectException:
    #except UnknownObjectException as e:
        print(f'Initial repo. adding read.me')
        repo_config = []
    
    #Get Image profiles
    n_profiles = getNetworkProfiles(baseurl,access_token,apiVersion)
    n_profiles_name_out = extract_values(n_profiles,'name')
    print(f'Pushing vRA site: {vra_site} Network Profiles {n_profiles_name_out}')

    dt = datetime.now()
    branch_name = 'vra-config-Network-Profiles-' + dt.strftime('%Y%m%d-%H-%M-%S')
    # Create new branch from main    
    source = repo.get_branch("main")
    repo.create_git_ref(ref=f"refs/heads/{branch_name}", sha=source.commit.sha)     

    n_filename = f'{vra_site}_network_profiles.json'
    file_path = f'vRAConfig/{n_filename}'
    print(f'vRA Network Profile file path in repo {file_path}')
    #Check If actions already in the repo
    
    matching_zone = next((item for item in repo_config if (item.name == n_filename)), False)
    if matching_zone:
        print(f"adding new version of vRA Network Profile: {file_path}")
        push(repo, file_path, "vRA Network Profiles Commit for {vra_site}", json.dumps(n_profiles), branch_name, update=True)
    else:
        print(f"adding new vRA site {vra_site} cloud zone")
        push(repo, file_path, "vRA Network Profiles Commit for {vra_site}", json.dumps(n_profiles), branch_name, update=False)
    
    

    # Create Pull Request
    if create_mr.lower() == 'true':    
        pr_title = f'vRA Network Profile realease {dt.strftime("%Y:%m:%d")}'
        print(f'Creating Pull request with title: {pr_title}')
        pr = repo.create_pull(title=pr_title, body=pr_title, head=branch_name, base="main")
        #pr.edit(state="closed")
    
    #set outputs

    out_puts = {
        'vRA_Network_Profiles': n_profiles_name_out
    }
    
    return out_puts