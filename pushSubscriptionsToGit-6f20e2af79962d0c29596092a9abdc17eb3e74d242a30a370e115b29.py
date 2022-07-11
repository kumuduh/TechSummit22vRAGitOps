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
        ###bearer = "Bearer "
        bearer = "Bearer " + req.json()["token"]
        #print(f'bearer token {bearer}')
    return bearer
    
def getEBS(baseurl,access_token,apiVersion):
    headers = {"Authorization":access_token}
    uri_filter = urllib.parse.quote(f"type ne 'SUBSCRIBABLE'")
    ebs_uri = f'/event-broker/api/subscriptions?apiVersion={apiVersion}&$filter={uri_filter}&page=0'
    print(f'Get EBS uri {ebs_uri}')
    ebs_respose = requests.get(f'{baseurl}{ebs_uri}',headers = headers, verify=False)
    if ebs_respose.status_code != 200:
        print(f'Failed to getvRA EBS')
    else:    
        ebs_Obj = ebs_respose.json()['content'] 
        if int(ebs_respose.json()['totalPages']) > 1:
            for page in range(1,ebs_respose.json()['totalPages']):
                ebs_uri = f'/event-broker/api/subscriptions?apiVersion={apiVersion}&$filter={uri_filter}&page={page}'
                ebs_respose = requests.get(f'{baseurl}{ebs_uri}',headers = headers, verify=False)
                ebs_Obj = ebs_Obj + ebs_respose.json()['content']    


    #print(f'Get EBS is successful. EBS {ebs_Obj}')        
    return ebs_Obj
    
def push(repo, path, message, content, branch, update=False):
    print(f'Pushing to github {path} with update {update}')

    if update:  # If file already exists, update it
        contents = repo.get_contents(path, ref="main")  # Retrieve old file to get its SHA and path
        repo.update_file(contents.path, message, content, contents.sha, branch=branch)  # Add, commit and push branch
    else:  # If file doesn't exist, create it
        repo.create_file(path, message, content, branch=branch)  # Add, commit and push branch


def handler(context, inputs):
    
    print('Executing Get vRA project Cloud Templates...')
    
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
        repo_ebs = repo.get_contents('subscriptions','main')     
        gitEBName = extract_values(repo_ebs,'path')
        print(f'Git Repo subscriptions path: {repo_ebs} \n')
    except UnknownObjectException:
        print(f'Initial repo.')
        repo_ebs = [] 
   
    #Get Event suscriptions
    ebs_Obj = getEBS(baseurl,access_token,apiVersion)
    #print(f'vRA subscriptions: {ebs_Obj}')
    active_ebs_objs = []    
    commit_actions = []

    dt = datetime.now()
    branch_name = 'vra-EBS-' + dt.strftime('%Y%m%d-%H-%M-%S')
    # Create new branch from main    
    source = repo.get_branch("main")
    repo.create_git_ref(ref=f"refs/heads/{branch_name}", sha=source.commit.sha)     

    for eb in ebs_Obj:
        if not eb['disabled']:
            active_ebs_objs.append(eb)
            eb_filename = f'{eb["name"]}.json'
            file_path = f'subscriptions/{eb_filename}'
            print(f'EBS file path in repo {file_path}')
            #Check If ebs already in the repo
            matching_ebs = next((item for item in repo_ebs if (item.name == eb_filename)), False)
            if matching_ebs:
                print(f"adding new version of ebs: {file_path}")
                push(repo, file_path, "vRA ABX Commit for EBS - {eb['name']}", json.dumps(eb), branch_name, update=True)
            else:
                print(f"adding new ebs {file_path}")
                push(repo, file_path, "vRA ABX Commit for EBS - {eb['name']}", json.dumps(eb), branch_name, update=False)
    
    

    # Create Pull Request
    if create_mr.lower() == 'true':    
        pr_title = f'vRA Event subscriptions realease {dt.strftime("%Y:%m:%d")}'
        print(f'Creating Pull request with title: {pr_title}')
        pr = repo.create_pull(title=pr_title, body=pr_title, head=branch_name, base="main")
        #pr.edit(state="closed")
    
    #set outputs
    ebs_out = extract_values(active_ebs_objs,'name')
 
    
    out_puts = {
        'ebs': ebs_out
    }
    
    return out_puts