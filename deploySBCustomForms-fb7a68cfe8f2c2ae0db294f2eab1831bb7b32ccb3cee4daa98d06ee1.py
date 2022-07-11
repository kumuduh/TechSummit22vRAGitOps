import json
import yaml
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
        if "name" in f_obj:
            print(f'Found custom form for Catalog item: {f_obj["name"]}')
            custom_forms.append(f_obj)
        else:
            print(f'Empty Form: {f_obj["message"]}')
    return custom_forms
     
def createSBCustomFrm(baseurl,access_token,apiVersion,frm_payload):
    headers = {'Content-Type': 'application/json','Accept': 'application/json','Authorization':access_token}
    frm_uri = f'/form-service/api/forms?apiVersion={apiVersion}'
    print(f'Create Form uri {frm_uri}')
    print(f'Form payload:\n {frm_payload}')
    frm_respose = requests.post(f'{baseurl}{frm_uri}', json=frm_payload, headers = headers, verify=False)
    print(f'Create SB Custom form response : {frm_respose}')
    if frm_respose.status_code > 400:
        print(f'Failed to create vRA SB Custom From')
    else:    
        print(f'Successfully created vRA SB Custom From')
   

def handler(context, inputs):
    
    print('Executing Deploy vRA SB Forms...')
    
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
        repo_forms = repo.get_contents('forms',git_branch)     
        print(f'Git Repo forms path: {repo_forms} \n')
    except UnknownObjectException:
        print(f'Initial repo.')
        repo_forms = []   
        
    
    #Get Forms
    #Get Catalog Items
    cat_items = getSBCatItems(baseurl,access_token,apiVersion)
    #Get Forms
    active_forms_Obj = getSBCustomForms(baseurl,access_token,apiVersion,cat_items)
    #print(f'vRA SB Forms: {forms_Obj}')


    for fm_dir in repo_forms:
        #print(fm_dir)
        fm_file = repo.get_contents(fm_dir.path,git_branch)
        #should always bluprint.yaml only
        print(f'Form yaml file path: {fm_dir.path}')
        if (fm_file.path.endswith('.yaml')):
            fm_raw =  repo.get_contents(fm_dir.path,git_branch).decoded_content
            try:
                fm_yaml = yaml.safe_load(fm_raw)
            except yaml.YAMLError as e:
                print(f'Err parsing : {e}')
                
            #print(f'Form YAML: {fm_yaml}')
            
            matching_frm = False
            src_id = None
            src_type = None
            for active_frm in active_forms_Obj:
                if (f'{active_frm["name"].upper()}.YAML' == fm_dir.name.upper()):
                    print(f'Found matching Form: {active_frm["name"]} in the Repo')
                    matching_frm = True
                    frm_name_for_payload = active_frm["name"]
                    src_id = active_frm['sourceId']
                    src_type = active_frm['sourceType']
                    break
            
            if matching_frm:
                print(f'Cloud Template custom Form : {fm_dir.name} is alreay in Service Broker. Update with new version')
    
                frm_str = fm_yaml
                frm_obj = {
                    "form": fm_yaml,
                    "name": frm_name_for_payload,
                    "status": "ON",
                    "type": "requestForm",
                    "sourceId": src_id,
                    "sourceType": src_type,
                    "formFormat": "YAML"
                }
                #Remove if for test frm
                if(fm_dir.name == "test Kumudu.yaml"):
                    print('Found test bp in vRA. update form')
                    createSBCustomFrm(baseurl,access_token,apiVersion,frm_obj)
                    
            else:
                print(f"No matching Custom form for Catalog item {fm_dir.name}. Sync skip !!")
    
    
    
    
    #set outputs
    frm_name = extract_values(active_forms_Obj,'name')
    
    out_puts = {
        'deployed_customForms': frm_name
    }
    
    return out_puts