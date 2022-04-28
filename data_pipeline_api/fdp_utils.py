import hashlib
import json
import logging
import os
import random
import uuid
from datetime import datetime
from typing import Any, Optional, Tuple

# from typing import BinaryIO, Union
from urllib.parse import urlsplit

import netCDF4
import requests
import yaml

from data_pipeline_api.exceptions import AttributeSizeError, DataSizeError


def get_first_entry(entries: list) -> dict:
    """
    get_first_entry helper function for get_entry that return first element

    exception handling is done in the main code

    Parameters
    ----------
    entries : list
        [response list from api]

    Returns
    -------
    dict
        [dictionary output from api]
    """
    return entries[0]


def get_entry(
    url: str,
    endpoint: str,
    query: dict,
    token: str = None,
    api_version: str = "1.0.0",
) -> list:
    """
    Internal function to retreive and item from the registry using a query
    Args:
        |   url: str of the registry url
        |   endpoint: endpoint (table)
        |   query: dict forming a query
        |   token: (optional) str of the registry token
    Returns:
        |   dict: responce from registry
    """
    headers = get_headers(token=token, api_version=api_version)

    # Remove api address from query
    for key in query:
        if isinstance(query[key], str):
            if url in query[key]:
                query[key] = extract_id(query[key])
        elif isinstance(query[key], dict):
            for _key in query[key]:
                if url in query[key][_key]:
                    query[key][_key] = extract_id(query[key][_key])
        elif isinstance(query[key], list):
            for i in range(len(query[key])):
                if url in query[key][i]:
                    query[key][i] = extract_id(query[key][i])

    if url[-1] != "/":
        url += "/"
    url += f"{endpoint}/?"
    _query = [f"{k}={v}" for k, v in query.items()]
    url += "&".join(_query)
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        raise ValueError(
            "Server responded with: "
            + str(response.status_code)
            + " Query = "
            + url
        )
    return response.json()["results"]


def get_entity(
    url: str,
    endpoint: str,
    id: int,
    token: str = None,
    api_version: str = "1.0.0",
) -> dict:
    """
    Internal function to get an item from the registry using it's id
    Args:
        |   url: str of the registry url
        |   enpoint: endpoint (table)
        |   id: id of the item
        |   token: (optional) str of the registry token
    Returns:
        |   dict: responce from registry
    """
    headers = get_headers(token=token, api_version=api_version)

    if url[-1] != "/":
        url += "/"
    url += f"{endpoint}/{id}"
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        raise ValueError(
            "Server responded with: "
            + str(response.status_code)
            + " Query = "
            + url
        )
    return response.json()


def extract_id(url: str) -> str:
    """
    Internal function to return the id from an api url
    Args:
        |   url: str of the api url
    Returns:
        |   str: id derrived from the url
    """
    split_url_path = urlsplit(url).path.split("/")
    output = [s for s in split_url_path if s != ""]
    if not output:
        raise IndexError(f"Unable to extract ID from registry URL: {url}")
    return output[-1]


def post_entry(
    url: str, endpoint: str, data: dict, token: str, api_version: str = "1.0.0"
) -> dict:
    """
    Internal function to post and entry on the registry
    Args:
        |   url: str of the registry url
        |   enpoint: str of the endpoint (table)
        |   data: a dictionary containing the data to be posted
        |   token: str of the registry token
    Returns:
        |   dict: responce from registry
    """
    headers = get_headers(
        request_type="post", token=token, api_version=api_version
    )

    if url[-1] != "/":
        url += "/"
    _url = url + endpoint + "/"
    _data = json.dumps(data)

    response = requests.post(_url, _data, headers=headers)

    if response.status_code == 409:
        logging.info("Entry Exists: Attempting to return Existing Entry")
        existing_entry = get_entry(url, endpoint, data)
        if not existing_entry:
            raise ValueError("Could not return existing Entry")
        return existing_entry[0]

    if response.status_code != 201:
        raise ValueError(f"Server responded with: {str(response.status_code)}")

    return response.json()


def patch_entry(
    url: str, data: dict, token: str, api_version: str = "1.0.0"
) -> dict:
    """
    Internal function to patch and entry on the registry
    Args:
        |   url: str of the url of what to be patched
        |   data: a dictionary containing the data to be patched
        |   token: str of the registry token
    Returns:
        |   dict: responce from registry
    """
    headers = get_headers(
        request_type="post", token=token, api_version=api_version
    )

    data_json = json.dumps(data)

    response = requests.patch(url, data_json, headers=headers)
    if response.status_code != 200:
        raise ValueError(f"Server responded with: {str(response.status_code)}")

    return response.json()


def get_headers(
    request_type: str = "get", token: str = None, api_version: str = "1.0.0"
) -> dict:
    """
    Internal function to return headers to be added to a request
    Args:
        |   request_type: (optional) type of request e.g. 'post' or 'get' defaults to 'get'
        |   token: (optional) token, if a token is supplied this will be added to the headers
        |   api_version: (optional) the version of the data registy to interact with, defaults to '1.0.0'
    Returns:
        |   dict: a dictionary of appropriate headers to be added to a request
    """
    headers = {"Accept": f"application/json; version={api_version}"}
    if token:
        headers["Authorization"] = f"token {token}"
    if request_type == "post":
        headers["Content-Type"] = "application/json"
    return headers


def post_storage_root(
    url: str, data: dict, token: str, api_version: str = "1.0.0"
) -> dict:
    """
    Internal function to post a storage root to the registry
    the function first adds file:// if the root is local
    Args:
        |   url: str the url for the storage root e.g. https://github.com/
    Returns:
        |   dict: repsonse from the local registy
    """
    if "local" in data and data["local"]:
        data["root"] = "file://" + data["root"]
    if data["root"][-1] != "/":
        data["root"] = data["root"] + "/"
    return post_entry(url, "storage_root", data, token, api_version)


def remove_local_from_root(root: str) -> str:
    """
    Internal function to remove prepending file:// from a given root
    Args:
        |   root: the root
    Returns:
        |   str: the root without file://
    """
    if "file://" in root:
        root = root.replace("file://", "")

    return root


def random_hash() -> str:
    """
    Internal function to generate a random unique hash

    Returns:
        |   str: 40 character randomly generated hash.
    """
    seed = datetime.now().timestamp() * random.uniform(1, 1000000)
    seed_encoded = str(seed).encode("utf-8")
    hashed = hashlib.sha1(seed_encoded)

    return hashed.hexdigest()


def get_file_hash(
    path: str,
) -> str:
    """
    Internal function to return a files sha1 hash
    Args:
        |   path: str file path
    Returns:
        |   str: sha1 hash
    """
    with open(path, "rb") as data:
        _data = data.read()
    # data = data.encode('utf-8')
    hashed = hashlib.sha1(_data)

    return hashed.hexdigest()


def read_token(token_path: str) -> str:
    """
    Internal function read a token from a given file
    Args:
        |   token_path: path to token
    Returns:
        |   str: token
    """
    with open(token_path) as token:
        _token = token.readline().strip()
    return _token


def get_token(token_path: str) -> str:
    """
    Internal function alias for read_token()
    Args:
        |   token_path: path to token
    Returns:
        |   str: token
    """
    return read_token(token_path)


def is_file(filename: str) -> bool:
    """
    Internal function to check whether a file exists
    Args:
        |   filename: file to check
    Returns:
        |   boolean: whether the file exists
    """
    return os.path.isfile(filename)


def is_yaml(filename: str) -> bool:
    """
    Internal function to check whether a file can be opened as a YAML file
    ! warning returns True if the file can be coerced into yaml format
    Args:
        |   filename: path to the yaml file
    Returns:
        |   boolean: can the file be coerced into a yaml format?
    """
    try:
        with open(filename, "r") as data:
            yaml.safe_load(data)
    except Exception as err:
        print(f"{type(err).__name__} was raised: {err}")
        return False
    return True


def is_valid_yaml(filename: str) -> bool:
    """
    Internal function validate whether a file exists and can be coerced into a yaml format
    Args:
        |   filename: path to the yaml file
    Returns:
        |   boolean: does the file exist and can it be coerced into a yaml format
    """
    return is_file(filename) & is_yaml(filename)


def generate_uuid() -> str:
    """
    Internal function similar to random hash
    Returns:
        |   str: a random unique identifier
    """
    return datetime.now().strftime("%Y%m-%d%H-%M%S-") + str(uuid.uuid4())


def get_handle_index_from_path(handle: dict, path: str) -> Optional[Any]:
    """
    Get an input or output handle index from a path
    usually generated by link_read or link_write

    Args:
        |   handle: the handle containing the index
        |   path: path as generated by link_read or link_write
    """
    tmp = None
    if "output" in handle:
        for output in handle["output"]:
            if handle["output"][output]["path"] == path:
                tmp = output
    if "input" in handle:
        for input in handle["input"]:
            if handle["input"][input]["path"] == path:
                tmp = input
    return tmp


# flake8: noqa C901
def register_issues(
    token: str, handle: dict
) -> dict:  # sourcery no-metrics skip: avoid-builtin-shadow
    """
    Internal function, should only be called from finalise.
    """

    api_url = handle["yaml"]["run_metadata"]["local_data_registry_url"]
    issues = handle["issues"]
    groups = {handle["issues"][i]["group"] for i in handle["issues"]}
    api_version = handle["yaml"]["run_metadata"]["api_version"]

    for group in groups:
        component_list = []
        issue = None
        severity = None
        for i in issues:
            if issues[i]["group"] == group:
                type = issues[i]["type"]
                issue = issues[i]["issue"]
                severity = issues[i]["severity"]
                index = issues[i]["index"]
                data_product = issues[i]["use_data_product"]
                component = issues[i]["use_component"]
                version = issues[i]["version"]
                namespace = issues[i]["use_namespace"]

                component_url = None
                object_id = None
                if type == "config":
                    object_id = handle["model_config"]
                elif type == "github_repo":
                    object_id = handle["code_repo"]

                elif type == "submission_script":
                    object_id = handle["submission_script"]
                if object_id:
                    component_url = get_entry(
                        url=api_url,
                        endpoint="object_component",
                        query={
                            "object": extract_id(object_id),
                            "whole_object": True,
                        },
                        api_version=api_version,
                    )[0]["url"]

                if index:
                    if "output" in handle:
                        for ii in handle["output"]:
                            if handle["output"][ii] == index:
                                if (
                                    "component_url"
                                    in handle["output"][ii].keys()
                                ):
                                    component_url = handle["output"][ii][
                                        "component_url"
                                    ]
                                else:
                                    logging.warning("No Component Found")
                    if "input" in handle:
                        for ii in handle["input"]:
                            if handle["input"][ii] == index:
                                if (
                                    "component_url"
                                    in handle["input"][ii].keys()
                                ):
                                    component_url = handle["input"][ii][
                                        "component_url"
                                    ]
                                else:
                                    logging.warning("No Component Found")

                if data_product:
                    current_namespace = get_entry(
                        url=api_url,
                        endpoint="namespace",
                        query={"name": namespace},
                        api_version=api_version,
                    )[0]["url"]

                    object = get_entry(
                        url=api_url,
                        endpoint="data_product",
                        query={
                            "name": data_product,
                            "version": version,
                            "namespace": extract_id(current_namespace),
                        },
                        api_version=api_version,
                    )[0]["object"]
                    object_id = extract_id(object)
                    if component:
                        component_url = get_entry(
                            url=api_url,
                            endpoint="object_component",
                            query={"name": component, "object": object_id},
                            api_version=api_version,
                        )
                    else:
                        component_obj = get_entry(
                            url=api_url,
                            endpoint="object_component",
                            query={"object": object_id, "whole_object": True},
                            api_version=api_version,
                        )
                        component_url = component_obj[0]["url"]

                if component_url:
                    component_list.append(component_url)

        # Register the issue:
        logging.info("Registering issue: {}".format(group))
        current_issue = post_entry(
            url=api_url,
            endpoint="issue",
            data={
                "severity": severity,
                "description": issue,
                "component_issues": component_list,
            },
            token=token,
            api_version=api_version,
        )
    return current_issue


def create_group(root_group: netCDF4.Group, group_name: str) -> None:
    """
    create_group
    creates a group inside a netcdf file

    Parameters
    ----------
    root_group : netCDF4.Group
        root group, the new group will be a child of this one
    group_name : str
        name of the child group
    """
    # no need to check if group_name exists as createGroup is idempotent
    _ = root_group.createGroup(group_name)


def create_nested_groups(root_group: netCDF4.Group, path: str) -> None:
    """
    create_nested_groups
    creates nested groups inside a netcdf file

    Parameters
    ----------
    root_group : netCDF4.Group
        root group, the new group will be a child of this one
    path : str
        nested groups in the form first/second/third/
    """

    groups = [grp for grp in path.split("/") if grp != ""]
    for group in groups:
        current = group
        create_group(root_group, current)
        root_group = root_group[current]


def create_variable_in_group(
    group: netCDF4.Group,
    variables_name: str,
    variable_data: Any,
    variable_type: str = "f",
) -> None:
    """
    create_variable_in_group
    creates a variable inside a group, i.e. x=[1,2,3]

    Parameters
    ----------
    group : netCDF4.Group
        group within the netcdf file where variables will be stored
    variables_name : str
        name of the variable
    variable_data : Any
        data
    variable_type : str, optional
        data type of the data, by default "f"
    """
    if variables_name in group.variables.keys():
        raise ValueError("variable already exists")

    var_dim = "dim"
    size = len(variable_data)
    xdim = group.createDimension(var_dim, size)
    xdim_v = group.createVariable(variables_name, variable_type, xdim.name)
    xdim_v[:] = variable_data


def create_1d_variables_in_group(
    group: netCDF4.Group,
    variables_name: list,
    variable_xdata: Any,
    data: list,
    data_types: list,
    variable_xname: str = "X",
    variable_xname_type: str = "f",
) -> None:
    """
    create_1d_variables_in_group
    given a list of variables in the form data=f(x) store them inside a group

    Parameters
    ----------
    group : netCDF4.Group
        group within the netcdf file where variables will be stored
    variables_name : list
        a list of variables to be stored
    variable_xdata : Any
        x indipendent componentdecimals
    data : list
        list of variables to be stored
    data_types : list
        list of types of the data inside the data variables
    variable_xname : str, optional
         name of the x component, by default "X"
    variable_xname_type : str, optional
         type of the x component, by default "f"
    """
    var_dim = f"{variable_xname}_dim"
    size = len(variable_xdata)
    if var_dim in group.dimensions.keys():
        raise ValueError(
            f"failed to create dimension. {var_dim} already exists inside {group}"
        )
    xdim = group.createDimension(var_dim, size)
    xdim_v = group.createVariable(
        variable_xname, variable_xname_type, xdim.name
    )
    xdim_v[:] = variable_xdata

    for i, name in enumerate(variables_name):
        if name in group.variables.keys():
            raise ValueError(
                f"failed to create variable. {name} already exists inside {group}"
            )
        data_v = group.createVariable(name, data_types[i], xdim.name)
        data_v[:] = data[i]


def create_2d_variables_in_group(
    group: netCDF4.Group,
    variables_name: list,
    variable_xdata: Any,
    variable_ydata: Any,
    data: list,
    data_types: list,
    variable_xname: str = "X",
    variable_xname_type: str = "f",
    variable_yname: str = "Y",
    variable_yname_type: str = "f",
) -> None:
    """
    create_2d_variables_in_group
    given a list of variables in the form data=f(x,y) store them inside a group

    Parameters
    ----------
    group : netCDF4.Group
        group within the netcdf file where variables will be stored
    variables_name : list
        a list of variables to be stored
    variable_xdata : Any
        x indipendent component
    variable_ydata : Any
        y indipendent component
    data : list
        list of variables to be stored
    data_types : list
        list of types of the data inside the data variables
    variable_xname : str, optional
        name of the x component, by default "X"
    variable_xname_type : str, optional
        type of the x component, by default "f"
    variable_yname : str, optional
        name of the y component, by default "Y"
    variable_yname_type : str, optional
        type of the y component, by default "f"
    """
    x_dim = f"{variable_xname}_dim"
    size = len(variable_xdata)
    if x_dim in group.dimensions.keys():
        raise ValueError(
            f"failed to create dimension. {x_dim} already exists inside {group}"
        )
    xdim = group.createDimension(x_dim, size)
    _ = group.createVariable(variable_xname, variable_xname_type, xdim.name)
    y_dim = f"{variable_yname}_dim"
    size = len(variable_ydata)
    if y_dim in group.dimensions.keys():
        raise ValueError(
            f"failed to create dimension. {y_dim} already exists inside {group}"
        )

    ydim = group.createDimension(y_dim, size)
    ydim_v = group.createVariable(
        variable_yname, variable_yname_type, ydim.name
    )
    ydim_v[:] = variable_ydata
    for i, name in enumerate(variables_name):
        if name in group.variables.keys():
            raise ValueError(
                f"failed to create variable. {name} already exists inside {group}"
            )
        data_v = group.createVariable(
            name, data_types[i], (xdim.name, ydim.name)
        )
        data_v[:] = data[i]


def create_3d_variables_in_group(
    group: netCDF4.Group,
    variables_name: list,
    variable_xdata: Any,
    variable_ydata: Any,
    variable_zdata: Any,
    data: list,
    data_types: list,
    variable_xname: str = "X",
    variable_xname_type: str = "f",
    variable_yname: str = "Y",
    variable_yname_type: str = "f",
    variable_zname: str = "Z",
    variable_zname_type: str = "f",
) -> None:
    """
    create_3d_variables_in_group
    given a list of variables in the form data=f(x,y,z) store them inside a group

    Parameters
    ----------
    group : netCDF4.Group
        group within the netcdf file where variables will be stored
    variables_name : list
        a list of variables to be stored
    variable_xdata : Any
        x indipendent component
    variable_ydata : Any
        y indipendent component
    variable_zdata : Any
        z indipendend component
    data : list
        list of variables to be stored
    data_types : list
        list of types of the data inside the data variables
    variable_xname : str, optional
        name of the x component, by default "X"
    variable_xname_type : str, optional
        type of the x component, by default "f"
    variable_yname : str, optional
        name of the y component, by default "Y"
    variable_yname_type : str, optional
        type of the y component, by default "f"
    variable_zname : str, optional
        name of the z component, by default "Z"
    variable_zname_type : str, optional
     type of the z component, by default "f"
    """
    x_dim = f"{variable_xname}_dim"
    size = len(variable_xdata)
    if x_dim in group.dimensions.keys():
        raise ValueError(
            f"failed to create dimension. {x_dim} already exists inside {group}"
        )

    xdim = group.createDimension(x_dim, size)
    _ = group.createVariable(variable_xname, variable_xname_type, xdim.name)

    y_dim = f"{variable_yname}_dim"

    size = len(variable_ydata)
    if y_dim in group.dimensions.keys():
        raise ValueError(
            f"failed to create dimension. {y_dim} already exists inside {group}"
        )
    ydim = group.createDimension(y_dim, size)
    ydim_v = group.createVariable(
        variable_yname, variable_yname_type, ydim.name
    )
    ydim_v[:] = variable_ydata

    z_dim = f"{variable_zname}_dim"
    size = len(variable_zdata)
    if z_dim in group.dimensions.keys():
        raise ValueError(
            f"failed to create dimension. {z_dim} already exists inside {group}"
        )
    zdim = group.createDimension(z_dim, size)
    zdim_v = group.createVariable(
        variable_zname, variable_zname_type, zdim.name
    )
    zdim_v[:] = variable_zdata

    for i, name in enumerate(variables_name):
        if name in group.variables.keys():
            raise ValueError(
                f"failed to create variable. {name} already exists inside {group}"
            )
        data_v = group.createVariable(
            name, data_types[i], (xdim.name, ydim.name, zdim.name)
        )
        data_v[:] = data[i]


def set_or_create_attr(
    var: netCDF4._netCDF4.Variable, attr_name: str, attr_data: Any
) -> None:
    """
    set_or_create_attr     setattr only sets existing netCDF4 attributes, any attributes it creates are attached to the python instance (not inside the dataset / file). Instead, you need to create a new attribute; without a method for directly creating attributes, you can use a workaround of creating an arbitrarily named attribute by directly setting it and then renaming it.

    Parameters
    ----------
    var : _type_
        input variable where the attribute will be set
    attr_name : _type_
        name of the attribute
    attr_data : _type_
        attribute data
    """
    """

    """
    if attr_name in var.ncattrs():
        var.setncattr(attr_name, attr_data)
        return
    var.UnusedNameAttribute = attr_data
    var.renameAttribute("UnusedNameAttribute", attr_name)


def create_nd_variables_in_group_w_attribute(
    group: netCDF4.Group,
    data_names: list,
    attribute_data: list,
    data: list,
    data_types: list,
    attribute_var_name: list,
    attribute_type: list,
    other_attribute_names: list = [None],
    other_attribute_data: list = [None],
    title_names: list = [None],
    dimension_names: list = [None],
) -> None:
    """
    create_nd_variables_in_group_w_attribute      given a list of data as f(x1,x2,...xi) will write them within a group of a netCDF file setting xi as attribute of each data.

     Default attributes as units and dimension are also set. User can also specify additional attributes.

    Parameters
    ----------
    group : netCDF4.Group
        existing group inside netcdf file where to store the data
    data_names : list
        list string describing the name of data to be stored
    attribute_data : list
        list variables to store as attributes of each data
    data : list
        list of data to store
    data_types : list
        list of types of the data to be stored
    attribute_var_name : list
        list of names of the attribute as they will be displayed/stored in the netcdf file
    attribute_type : list
        list of type of each attribute
    other_attribute_names : list, optional
        list of names of optional attributes, by default [None]
    other_attribute_data : list, optional
        list of data for each of optional attributes, by default [None]
    title_names : list, optional
        default title attribute, by default [None]
    dimension_names : list, optional
        default dimension attribute, by default [None]

    """
    if len(title_names) == 1 and not title_names[0]:
        title_names = ["Unknown" for _ in range(len(data))]
    if len(dimension_names) == 1 and not dimension_names[0]:
        dimension_names = ["Unknown" for _ in range(len(data))]

    if (
        not len(attribute_data)
        == len(attribute_var_name)
        == len(attribute_type)
    ):
        raise AttributeSizeError(
            "Invalid Operation - check size of data - all attribute inputs must be of same size"
        )
    if not len(data) == len(data_names) == len(data_types):
        raise DataSizeError("Invalid Operation - check size of data")
    if title_names:
        if len(title_names) != len(data):
            raise AttributeSizeError(
                "Invalid Operation - check size of title names attribute"
            )
    if dimension_names:
        if len(dimension_names) != len(data):
            raise AttributeSizeError(
                "Invalid Operation - check size of dimension names attribute"
            )
    for dd, value in enumerate(data):

        for dim in range(len(value.shape)):
            if value.shape[dim] != len(attribute_data[dim]):
                raise ValueError(
                    f"size of {attribute_var_name[dim]} incompatible with data"
                )
    data_dim: Tuple = tuple()
    for dim in range(len(attribute_data)):
        var_dim = attribute_var_name[dim] + "_dim"
        if var_dim in group.dimensions.keys():
            raise ValueError(
                f"failed to create dimension. {var_dim} already exists inside {group}"
            )
        vars()[attribute_var_name[dim] + "_dim"] = group.createDimension(
            var_dim, len(attribute_data[dim])
        )
        data_dim = data_dim + (vars()[attribute_var_name[dim] + "_dim"].name,)
    for i, name in enumerate(data_names):
        if name in group.variables.keys():
            raise ValueError(
                f"failed to create variable. {name} already exists inside {group}"
            )
        data_v = group.createVariable(name, data_types[i], data_dim)
        data_v[:] = data[i]

    for i, name in enumerate(data_names):
        for attr, value in enumerate(attribute_var_name):

            set_or_create_attr(
                group[name], attribute_var_name[attr], attribute_data[attr]
            )

        set_or_create_attr(group[name], "title", title_names[i])
        set_or_create_attr(group[name], "units", dimension_names[i])

        if all([True if x != None else False for x in other_attribute_names]):
            if len(other_attribute_names) != len(other_attribute_data):
                raise DataSizeError(
                    "incorrect data - check size of additional attributes"
                )

            for i, attr in enumerate(other_attribute_names):
                set_or_create_attr(
                    group[name], str(attr), other_attribute_data[i]
                )
