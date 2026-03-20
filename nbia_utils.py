import io
import os
from typing import Union, List, Optional
import logging
import requests
import pandas as pd
from datetime import datetime
from datetime import timedelta
from enum import Enum

token_url = "https://keycloak-stg.dbmi.cloud/auth/realms/TCIA/protocol/openid-connect/token"

class StopExecution(Exception):
    def _render_traceback_(self):
        pass

_log = logging.getLogger(__name__)
logging.basicConfig(
    format='%(asctime)s:%(levelname)s:%(message)s',
    level=logging.INFO
)

def log_request_exception(err: requests.exceptions.RequestException) -> None:
    if isinstance(err, requests.exceptions.HTTPError):
        if err.response is not None:
            status_code = err.response.status_code
            if status_code == 401:
                _log.error(f"Authentication Error: {err}. Status code: 401. Unauthorized access.")
            elif status_code == 403:
                _log.error(f"Permission Error: {err}. Status code: 403. Forbidden access.")
            elif status_code == 404:
                _log.error(f"Resource Not Found: {err}. Status code: 404.")
            else:
                _log.error(f"HTTP Error: {err}. Status code: {status_code}.")
        else:
            _log.error(f"HTTP Error with no response: {err}")
    elif isinstance(err, requests.exceptions.ConnectionError):
        _log.error(f"Connection Error: {err}. Unable to reach the server.")
    elif isinstance(err, requests.exceptions.Timeout):
        _log.error(f"Timeout Error: {err}. The request timed out.")
    else:
        _log.error(f"Request Exception: {err}. An unknown error occurred.")

def setApiUrl(endpoint, api_url = "nbia"):
    if api_url == "nlst":
        if 'nlst_token_exp_time' not in globals():
            getToken(user="nbia_guest", api_url="nlst")
        if 'nlst_token_exp_time' in globals() and datetime.now() > nlst_token_exp_time:
            refreshToken(api_url = "nlst")
    else:
        if 'token_exp_time' in globals() and datetime.now() > token_exp_time:
            refreshToken()

    if not api_url:
        api_url = "nbia"

    valid_api_urls = ["nbia", "nlst"]
    if api_url not in valid_api_urls:
        raise ValueError(f"Invalid api_url '{api_url}'. Must be one of: {valid_api_urls}")

    hostname = f"https://{api_url}.cancerimagingarchive.net/nbia-api/services"

    if endpoint in ["getAdvancedQCSearch", "getCollectionDescriptions", "createSharedList", "getAdvancedQCCriteria"]:
        base_url = f"{hostname}/"
    elif endpoint == "getContentsByName":
        base_url = f"{hostname}/v1/"
    else:
        base_url = f"{hostname}/v4/"

    return base_url

def getToken(user: str = "", pw: str = "", api_url: str = "", return_values: bool = False) -> Union[tuple, int, None]:
    global token_exp_time, api_call_headers, access_token, refresh_token, id_token
    global nlst_token_exp_time, nlst_api_call_headers, nlst_access_token, nlst_refresh_token, nlst_id_token

    if user != "":
        userName = user
    else:
        userName = input("Enter User: ")

    if pw == "":
        import getpass
        passWord = getpass.getpass(prompt='Enter Password: ')
    else:
        passWord = pw

    try:
        params = {'client_id': 'nbia',
                  'scope': 'openid',
                  'grant_type': 'password',
                  'username': userName,
                  'password': passWord
                 }

        data = requests.post(token_url, data=params)
        data.raise_for_status()
        response_json = data.json()

        tmp_access_token = response_json["access_token"]
        expires_in = response_json["expires_in"]
        tmp_id_token = response_json["id_token"]
        current_time = datetime.now()
        tmp_token_exp_time = current_time + timedelta(seconds=expires_in)
        tmp_api_call_headers = {'Authorization': 'Bearer ' + tmp_access_token}
        tmp_refresh_token = response_json["refresh_token"]

        if api_url == "nlst":
            nlst_access_token = tmp_access_token
            nlst_token_exp_time = tmp_token_exp_time
            nlst_api_call_headers = tmp_api_call_headers
            nlst_refresh_token = tmp_refresh_token
            nlst_id_token = tmp_id_token
            _log.info(f'Success - NLST Token saved and expires at {nlst_token_exp_time}')
        else:
            access_token = tmp_access_token
            token_exp_time = tmp_token_exp_time
            api_call_headers = tmp_api_call_headers
            refresh_token = tmp_refresh_token
            id_token = tmp_id_token
            _log.info(f'Success - Token saved and expires at {token_exp_time}')

        if return_values:
            return tmp_api_call_headers, tmp_access_token, tmp_token_exp_time, tmp_refresh_token, tmp_id_token
        else:
            return 200
    except requests.exceptions.RequestException as err:
        log_request_exception(err)
        raise StopExecution

def refreshToken(api_url: str = "primary", return_values: bool = False) -> Union[tuple, None]:
    global token_exp_time, api_call_headers, access_token, refresh_token, id_token
    global nlst_token_exp_time, nlst_api_call_headers, nlst_access_token, nlst_refresh_token, nlst_id_token

    try:
        if api_url == "nlst":
            tmp_token = nlst_refresh_token
        else:
            tmp_token = refresh_token
    except NameError:
        _log.error("No token found. Create one using getToken().")
        raise StopExecution

    try:
        params = {
            'client_id': 'nbia',
            'grant_type': 'refresh_token',
            'refresh_token': tmp_token
        }

        response = requests.post(token_url, data=params)
        response.raise_for_status()
        data = response.json()
        tmp_access_token = data.get("access_token")
        expires_in = data.get("expires_in")
        tmp_id_token = data.get("id_token")

        current_time = datetime.now()
        tmp_token_exp_time = current_time + timedelta(seconds=expires_in)
        tmp_api_call_headers = {'Authorization': 'Bearer ' + tmp_access_token}
        tmp_refresh_token = data.get("refresh_token")

        if api_url == "nlst":
            nlst_access_token = tmp_access_token
            nlst_token_exp_time = tmp_token_exp_time
            nlst_api_call_headers = tmp_api_call_headers
            nlst_refresh_token = tmp_refresh_token
            nlst_id_token = tmp_id_token
        else:
            access_token = tmp_access_token
            token_exp_time = tmp_token_exp_time
            api_call_headers = tmp_api_call_headers
            refresh_token = tmp_refresh_token
            id_token = tmp_id_token

        if return_values:
            return tmp_api_call_headers, tmp_access_token, tmp_token_exp_time, tmp_refresh_token, tmp_id_token
        else:
            return None
    except requests.exceptions.RequestException as err:
        log_request_exception(err)
        raise StopExecution

def queryData(endpoint: str, options: dict, api_url: str, format: str = "json", method: str = "GET", param: Optional[dict] = None) -> Optional[Union[dict, pd.DataFrame]]:
    base_url = setApiUrl(endpoint, api_url)
    url = f"{base_url}{endpoint}"
    response = None

    try:
        if endpoint in ["getAdvancedQCSearchCriteria", "getAdvancedQCSearch", "getSeriesQCInfo"]:
            if 'api_call_headers' not in globals() or not globals()['api_call_headers']:
                 _log.error(f"Endpoint '{endpoint}' requires authentication. Please run getToken() first.")
                 return None

        headers = nlst_api_call_headers if api_url == "nlst" else globals().get('api_call_headers', {})

        if method.upper() == "POST":
            _log.info(f'Calling {endpoint} with parameters {param}')
            response = requests.post(url, headers=headers, data=param)
        else:
            _log.info(f'Calling {endpoint} with parameters {options}')
            response = requests.get(url, params=options, headers=headers)

        response.raise_for_status()
        if not response.content.strip():
            _log.info("No results found.")
            return None

        try:
            data = response.json()
        except ValueError:
            if format.lower() in ["df", "csv"]:
                try:
                    df = pd.read_csv(io.StringIO(response.text))
                    return df
                except Exception as e:
                    _log.error(f"Failed to parse response. Error: {e}")
                    return None
            else:
                 return None

        if format.lower() == "df":
            return pd.DataFrame(data)
        else:
            return data
    except requests.exceptions.RequestException as err:
        log_request_exception(err)
        return None

def getAdvancedQCCriteria(api_url="nbia", format="json"):
    return queryData(endpoint="getAdvancedQCCriteria", options={}, api_url=api_url, format=format, method="GET")

_criteria_cache = None

def _fetch_and_parse_criteria(api_url="nbia", force_refresh: bool = False) -> dict:
    global _criteria_cache
    if force_refresh:
        _criteria_cache = None
    if _criteria_cache is not None:
        return _criteria_cache

    all_criteria_data = getAdvancedQCCriteria(api_url=api_url)
    if not all_criteria_data:
        _criteria_cache = {}
        return _criteria_cache

    parsed_criteria = {}
    for criteria_group in all_criteria_data:
        parent_name = criteria_group.get("parentMenuName")
        if parent_name and "criteriaObjects" in criteria_group and criteria_group["criteriaObjects"]:
            try:
                data_list = criteria_group["criteriaObjects"][0]["configuration"]["dynamicQueryCriteriaListData"]
                parsed_criteria[parent_name] = data_list
            except (KeyError, IndexError):
                continue
    _criteria_cache = parsed_criteria
    return _criteria_cache

def getCollections(format: str = "list", api_url="nbia", force_refresh: bool = False):
    all_criteria = _fetch_and_parse_criteria(api_url=api_url, force_refresh=force_refresh)
    collection_data = all_criteria.get("Collection", [])

    # Process collection names to remove site information (e.g., Collection//Site -> Collection)
    processed_collections = sorted(list(set([c.split('//')[0] for c in collection_data])))

    if format.lower() in ["dataframe", "df"]:
        # Maintain the original breakdown for dataframe format if needed,
        # but the request implies we should return only the collection name.
        collections, sites = [], []
        for item in collection_data:
            parts = item.split('//')
            collections.append(parts[0])
            sites.append(parts[1] if len(parts) > 1 else None)
        return pd.DataFrame({"Collection": collections, "Site": sites})

    # Return as list of dicts with 'Collection' key, using only unique collection names
    return [{"Collection": c} for c in processed_collections]

def getAdvancedQCSearch(criteria_values, api_url="", format="", input_type={}):
    input_type_map = {
        "collection": "list", "qcstatus": "list", "released": "list", "batchnumber": "list",
        "complete": "list", "patientID": "commaSeperatedList", "submissiondate": "dateRange",
        "studyUID": "commaSeperatedList", "seriesUID": "commaSeperatedList", "studyDate": "dateRange",
        "seriesDesc": "contains", "modality": "list", "manufacturer": "list",
    }
    endpoint = "getAdvancedQCSearch"
    param = {}
    counter = 0
    for item in criteria_values:
        if len(item) == 2:
            criteria, values = item
            boolean_op = "AND"
        else:
            raise ValueError("Each item in criteria_values must be a tuple of 2 elements.")
        if not isinstance(values, list):
            values = [values]
        for value in values:
            param[f"criteriaType{counter}"] = criteria
            param[f"inputType{counter}"] = input_type.get(criteria, input_type_map.get(criteria, "text"))
            param[f"value{counter}"] = value
            param[f"boolean{counter}"] = boolean_op
            counter += 1
    return queryData(endpoint=endpoint, options=None, api_url=api_url, format=format, method="POST", param=param)

def getStudy(collection = "", patientId = "", studyUid = "", api_url = "", format = ""):
    endpoint = "getPatientStudy"
    options = {}
    if collection:
        options['Collection'] = collection
    if patientId:
        options['PatientID'] = patientId
    if studyUid:
        options['StudyInstanceUID'] = studyUid

    data = queryData(endpoint, options, api_url, format)

    # If returning a DataFrame, standardize column names
    if isinstance(data, pd.DataFrame):
        column_mapping = {
            'StudyInstanceUID': 'Study UID',
            'ImageCount': 'Number of images'
        }
        data.rename(columns=column_mapping, inplace=True)
    elif isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
        # If returning a list of dicts, standardize keys
        for item in data:
            if 'StudyInstanceUID' in item:
                item['Study UID'] = item.pop('StudyInstanceUID')
            if 'ImageCount' in item:
                item['Number of images'] = item.pop('ImageCount')

    return data

def getSeriesList(uids: List[str], api_url: str = "", format: str = "df") -> Optional[pd.DataFrame]:
    chunk_size = 10000
    chunked_uids = [uids[i:i + chunk_size] for i in range(0, len(uids), chunk_size)]
    dfs = []
    endpoint = "getSeriesMetadata"
    for chunk in chunked_uids:
        uidList = ",".join(chunk)
        param = {'list': uidList}
        df_chunk = queryData(endpoint=endpoint, options=None, api_url=api_url, format="df", method="POST", param=param)
        if df_chunk is not None and not df_chunk.empty:
            dfs.append(df_chunk)
    if not dfs:
        return None
    df = pd.concat(dfs, ignore_index=True)
    column_mapping = {
        'Patient ID': 'PatientID',
        'PatientID': 'PatientID',
        'Study Instance UID': 'Study UID',
        'StudyInstanceUID': 'Study UID',
        'Series Instance UID': 'SeriesInstanceUID',
        'SeriesInstanceUID': 'SeriesInstanceUID',
        'Study Date': 'StudyDate',
        'Series Date': 'SeriesDate',
        'Image Count': 'Number of images',
        'ImageCount': 'Number of images',
        'Number of Images': 'Number of images',
        'File Size': 'FileSize',
        'Date Released': 'DateReleased',
        'Body Part Examined': 'BodyPartExamined',
        'Series Description': 'SeriesDescription',
        'Manufacturer Model Name': 'ManufacturerModelName',
        'Software Versions': 'SoftwareVersions',
        'License Name': 'LicenseName',
        'License URI': 'LicenseURI',
        'Collection URI': 'DataDescriptionURI',
    }
    df.rename(columns=column_mapping, inplace=True)
    return df
