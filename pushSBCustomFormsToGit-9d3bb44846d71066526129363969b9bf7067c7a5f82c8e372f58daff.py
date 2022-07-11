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
        ###bearer = "Bearer "
        bearer = "Bearer " + req.json()["token"]
        #print(f'bearer token {bearer}')
    return bearer
    
def getSBCatItems(baseurl,access_token,apiVersion):
    headers = {"Authorization":access_token}
    cat_uri = f'/catalog/api/admin/items?apiVersion={apiVersion}&page=0'
    print(f'Get Catalog Items uri {cat_uri}')
    cat_respose = requests.get(f'{baseurl}{cat_uri}',headers = headers, verify=False)
    if cat_respose.status_code != 200:
        print(f'Failed to get vRA SB Catalog items')
    else:    
        cat_Obj = cat_respose.json()['content'] 
        if int(cat_respose.json()['totalPages']) > 1:
            for page in range(1,cat_respose.json()['totalPages']):
                cat_uri = f'/catalog/api/admin/items?apiVersion={apiVersion}&page={page}'
                cat_respose = requests.get(f'{baseurl}{cat_uri}',headers = headers, verify=False)
                cat_Obj = cat_Obj.append(cat_respose.json()['content'])    


    #print(f'Get Catalog items is successful. Items {cat_Obj}') 
    return cat_Obj


def getSBCustomForms(baseurl,access_token,apiVersion,cat_items):
    custom_forms = []
    headers = {"Authorization":access_token}
    form_uri = f'/form-service/api/forms/fetchBySourceAndType?apiVersion={apiVersion}' 
    for cat in cat_items:
        form_resp =  requests.get(f'{baseurl}{form_uri}',headers = headers, verify=False,params={'formFormat': 'YAML','formType': 'requestForm','sourceId': cat['id'], 'sourceType': cat['type']['id']})
        #custom_forms.append(json.loads(form_resp.content))
        f_obj = form_resp.json()
        #Can validate status='ON'
        if "name" in f_obj:
            print(f'Found custom form for Catalog item: {f_obj["name"]}')
            custom_forms.append(f_obj)
        else:
            print(f'Empty Form: {f_obj["message"]}')
    return custom_forms
    
def push(repo, path, message, content, branch, update=False):
    print(f'Pushing to github {path} with update {update}')

    if update:  # If file already exists, update it
        contents = repo.get_contents(path, ref="main")  # Retrieve old file to get its SHA and path
        repo.update_file(contents.path, message, content, contents.sha, branch=branch)  # Add, commit and push branch
    else:  # If file doesn't exist, create it
        repo.create_file(path, message, content, branch=branch)  # Add, commit and push branch


def handler(context, inputs):
    
    print('Executing Get vRA Service Broker Custom Forms...')
    
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
        repo_forms = repo.get_contents('forms','main')     
        gitfrmName = extract_values(repo_forms,'ContentFile')
        print(f'Git Repo Forms path: {repo_forms} \n')
        print(f'Git Repo Forms path names: {gitfrmName} \n')
    except UnknownObjectException:
    #except UnknownObjectException as e:
        print(f'Initial repo. adding read.me')
        repo_forms = []
    
    #Get Catalog Items
    cat_items = getSBCatItems(baseurl,access_token,apiVersion)
    #Get Forms
    forms_Obj = getSBCustomForms(baseurl,access_token,apiVersion,cat_items)
    #print(f'vRA SB Forms: {forms_Obj}')
    active_frm_objs = []    
    commit_actions = []

    dt = datetime.now()
    branch_name = 'vra-CustomForms-' + dt.strftime('%Y%m%d-%H-%M-%S')
    # Create new branch from main    
    source = repo.get_branch("main")
    repo.create_git_ref(ref=f"refs/heads/{branch_name}", sha=source.commit.sha)     

    for frm in forms_Obj:
        active_frm_objs.append(frm)
        frm_filename = f'{frm["name"]}.yaml'
        file_path = f'forms/{frm_filename}'
        print(f'SB Form file path in repo {file_path}')
        #Check If actions already in the repo
        matching_frm = next((item for item in repo_forms if (item.name == frm_filename)), False)
        if matching_frm:
            print(f"adding new version of Form: {file_path}")
            push(repo, file_path, "vRA Form Commit for {frm['name']}", json.dumps(frm['form']), branch_name, update=True)
        else:
            print(f"adding new Form {file_path}")
            push(repo, file_path, "vRA Form Commit for {frm['name']}", json.dumps(frm['form']), branch_name, update=False)
    
    

    # Create Pull Request
    if create_mr.lower() == 'true':    
        pr_title = f'vRA SB Form realease {dt.strftime("%Y:%m:%d")}'
        print(f'Creating Pull request with title: {pr_title}')
        pr = repo.create_pull(title=pr_title, body=pr_title, head=branch_name, base="main")
        #pr.edit(state="closed")
    
    #set outputs
    frm_out = extract_values(active_frm_objs,'name')
 
    
    out_puts = {
        'frms': frm_out
    }
    
    return out_puts