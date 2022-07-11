import json
import urllib.parse
import requests
from datetime import datetime
from github import Github, GithubException, UnknownObjectException

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

def getCSVariables(baseurl,access_token,apiVersion):
    headers = {"Authorization":access_token}
    var_uri = f'/codestream/api/variables?apiVersion={apiVersion}&page=0'
    var_Obj = {}
    print(f'Get CS vars uri {var_uri}')
    var_respose = requests.get(f'{baseurl}{var_uri}',headers = headers, verify=False)
    if var_respose.status_code != 200:
        print(f'Failed to get vRA CS vars')
    else:    
        var_Obj = var_respose.json()['documents'] 
    
    return var_Obj

def push(repo, path, message, content, branch, update=False):
    print(f'Pushing to github {path} with update {update}')

    if update:  # If file already exists, update it
        contents = repo.get_contents(path, ref="main")  # Retrieve old file to get its SHA and path
        repo.update_file(contents.path, message, content, contents.sha, branch=branch)  # Add, commit and push branch
    else:  # If file doesn't exist, create it
        repo.create_file(path, message, content, branch=branch)  # Add, commit and push branch


def handler(context, inputs):
    
    print('Executing get CS vars ...')
    
    #Get inputs
    apiVersion = inputs['apiVersion']
    baseurl = inputs['vraBaseUrl']
    refToken = inputs['vraAPIToken']    
    project_name = inputs['projectName']
    
    #Get vRA access token
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
        repo_cs = repo.get_contents('codestream','main')     
        gitEBName = extract_values(repo_cs,'path')
        print(f'Git Repo codestream path: {repo_cs} \n')
    except UnknownObjectException:
        print(f'Initial repo.')
        repo_cs = [] 
        
    cs_vars = getCSVariables(baseurl,access_token,apiVersion)
    
    cs_vars_keys = cs_vars.keys()
    cs_var_out = []
    
    #Get CS Vars
    for cs_var in cs_vars:
        #print (f"CS var name: {cs_vars['cs_var']['name']}")
        #print(f'CS var {cs_vars.get(cs_var)}')
        #print(f'CS var {cs_vars[cs_var]}')
        cs_v = {
            "name": cs_vars[cs_var]['name'],
            "description": cs_vars[cs_var]['description'],
            "type": cs_vars[cs_var]['type']
        }
        if (cs_vars[cs_var]['type'] == "REGULAR"):
            cs_v["value"] = cs_vars[cs_var]['value']
        else:
            cs_v["value"] = ""
        cs_var_out.append(cs_v)

    #Prepare to commit
    dt = datetime.now()
    branch_name = 'vra-EBS-' + dt.strftime('%Y%m%d-%H-%M-%S')
    # Create new branch from main    
    source = repo.get_branch("main")
    repo.create_git_ref(ref=f"refs/heads/{branch_name}", sha=source.commit.sha)     
    
    cs_var_filename = f'cs_var.json'
    file_path = f'codestream/{cs_var_filename}'
    print(f'codestream file path in repo {file_path}')
    
    #Check If ebs already in the repo
    matching_cs_var = next((item for item in repo_cs if (item.name == cs_var_filename)), False)
    if matching_cs_var:
        print(f"adding new version of CS Var file: {file_path}")
        push(repo, file_path, "CS var file Update", json.dumps(cs_var_out), branch_name, update=True)
    else:
        print(f"adding new CS Var file {file_path}")
        push(repo, file_path, "CS var file Create", json.dumps(cs_var_out), branch_name, update=False)
    
    

    # Create Pull Request
    if create_mr.lower() == 'true':    
        pr_title = f'codestream realease {dt.strftime("%Y:%m:%d")}'
        print(f'Creating Pull request with title: {pr_title}')
        pr = repo.create_pull(title=pr_title, body=pr_title, head=branch_name, base="main")
        #pr.edit(state="closed")
    

    #set outputs
    out_puts = {
        'cs_vars': cs_var_out
    }
    
    return out_puts