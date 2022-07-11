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
    project_name = inputs['projectName']
    #gitlab_token = context.getSecret(inputs["gitLabToken"])
    github_token = inputs["gitHubToken"]
    #print(f'GitLab Token: {github_token}')
    git_repo = inputs['gitRepo']
    create_mr = inputs['createMergeRequest']
    
    #git access
    g = Github(github_token)
    repo = g.get_repo(git_repo)
    
    #git_project = gl.projects.get(git_project_id)
    print(f'Git Repo {repo.name} \n')
    
    try:
        repo_blueprints = repo.get_contents('blueprints','main')     
        print(f'Git Repo blueprints path: {repo_blueprints} \n')
    except UnknownObjectException:
        print(f'Initial repo.')
        repo_blueprints = []   
        
    
    #Get Blueprint 
    uri_filter = urllib.parse.quote(f"projectName eq '{project_name}'")
    blueprints_uri = f'/blueprint/api/blueprints/?apiVersion={apiVersion}&$filter={uri_filter}'
    project_bp_obj = vRAC_RESTCall(context,'GET',blueprints_uri,'')
    project_bp_ids = extract_values(project_bp_obj,'id')
    commit_actions = []

    dt = datetime.now()
    branch_name = 'vra-cloudTemplates-' + dt.strftime('%Y%m%d-%H-%M-%S')
    # Create new branch from main    
    source = repo.get_branch("main")
    repo.create_git_ref(ref=f"refs/heads/{branch_name}", sha=source.commit.sha)     
    for bp in project_bp_obj["content"]:
        #Get BP Content
        bp_uri = f'/blueprint/api/blueprints/{bp["id"]}'
        bp_obj = vRAC_RESTCall(context,'GET',bp_uri,'')
        blueprint_content = bp_obj['content']
        file_path = f'blueprints/{bp["name"]}/blueprint.yaml'
        
        #Check If BP already in the repo
        #if repo_blueprints:
        matching_blueprint = next((item for item in repo_blueprints if ((item.type == "dir") and (item.name == bp['name']))), False)
        if matching_blueprint:
            print(f"adding new version of cloud template: {file_path}")
            push(repo, file_path, "vRA ABX Commit for BP - {bp['name']}", blueprint_content, branch_name, update=True)
        else:
            print(f"adding new cloud template {file_path}")
            push(repo, file_path, "vRA ABX Commit for BP - {bp['name']}", blueprint_content, branch_name, update=False)
        
    

    # Create Pull Request
    if create_mr.lower() == 'true':
        pr_title = f'vRA Cloud Template realease {dt.strftime("%Y:%m:%d")}'
        print(f'Creating Pull request with title: {pr_title}')
        pr = repo.create_pull(title=pr_title, body=pr_title, head=branch_name, base="main")
        #pr.edit(state="closed")
    
    #set outputs
    project_bp_name = extract_values(project_bp_obj,'name')
    
    out_puts = {
        'pushed_blueprints': project_bp_name
    }
    
    return out_puts