# -*- coding: utf-8 -*-
from __future__ import (absolute_import, division, print_function)

import pytest
from itertools import count
import json

from ansible.module_utils.six import StringIO
from units.modules.utils import (
    AnsibleExitJson, AnsibleFailJson, fail_json, exit_json, set_module_args)
from ansible.modules.identity.keycloak import keycloak_link_group_role
from ansible.module_utils.six.moves.urllib.error import HTTPError


def create_wrapper(text_as_string):
    """Allow to mock many times a call to one address.
    Without this function, the StringIO is empty for the second call.
    """
    def _create_wrapper():
        return StringIO(text_as_string)
    return _create_wrapper


def build_mocked_request(get_id_user_count, response_dict):
    def _mocked_requests(*args, **kwargs):
        try:
            url = args[0]
        except IndexError:
            url = kwargs['url']
        method = kwargs['method']
        future_response = response_dict.get(url, None)
        return get_response(future_response, method, get_id_user_count)
    return _mocked_requests


def get_response(object_with_future_response, method, get_id_call_count):
    if callable(object_with_future_response):
        return object_with_future_response()
    if isinstance(object_with_future_response, dict):
        return get_response(
            object_with_future_response[method], method, get_id_call_count)
    if isinstance(object_with_future_response, list):
        try:
            call_number = get_id_call_count.__next__()
        except AttributeError:
            # manage python 2 versions.
            call_number = get_id_call_count.next()
        return get_response(
            object_with_future_response[call_number], method, get_id_call_count)
    return object_with_future_response


def raise_404(url):
    def _raise_404():
        raise HTTPError(url=url, code=404, msg='does not exist', hdrs='', fp=StringIO(''))
    return _raise_404


CONNECTION_DICT = {
    'http://keycloak.url/auth/realms/master/protocol/openid-connect/token': create_wrapper('{"access_token": "a long token"}'),
}


@pytest.fixture
def mock_doing_nothing_urls(mocker):
    doing_nothing_urls = CONNECTION_DICT.copy()
    doing_nothing_urls.update({
        'http://keycloak.url/auth/admin/realms/master/groups': create_wrapper(
            json.dumps([{'id': '111-111', 'name': 'one_group'}])),
        'http://keycloak.url/auth/admin/realms/master/groups/111-111': create_wrapper(
            json.dumps({'id': '111-111', 'name': 'one_group'})),
        'http://keycloak.url/auth/admin/realms/master/groups/111-111/role-mappings/realm/composite': create_wrapper(
            json.dumps({})),
        'http://keycloak.url/auth/admin/realms/master/roles/one_role': create_wrapper(
            json.dumps({'id': '222-222', 'name': 'one_role'})),
        'http://keycloak.url/auth/admin/realms/master/clients?clientId=one_client': create_wrapper(
            json.dumps([{'id': '333-333', 'clientId': 'one_client'}])),
        'http://keycloak.url/auth/admin/realms/master/clients/333-333/roles/role_in_client': create_wrapper(
            json.dumps({'id': '444-444', 'name': 'role_in_client'})),
        'http://keycloak.url/auth/admin/realms/master/groups/111-111/role-mappings/clients/333-333/composite': create_wrapper(
            json.dumps([])),
    })
    return mocker.patch(
        'ansible.module_utils.keycloak.open_url',
        side_effect=build_mocked_request(count(), doing_nothing_urls),
        autospec=True
    )


@pytest.mark.parametrize('extra_arguments, waited_message', [
    ({'role_name': 'one_role'},
     'Links between one_group and one_role does not exist, doing nothing.'),
    ({'role_name': 'role_in_client', 'client_id': 'one_client'},
     'Links between one_group and role_in_client in one_client does_not_exist, doing nothing.')
], ids=['role in realm master', 'role in client'])
def test_state_absent_without_link_should_not_do_something(
        monkeypatch, extra_arguments, waited_message, mock_doing_nothing_urls):
    monkeypatch.setattr(keycloak_link_group_role.AnsibleModule, 'exit_json', exit_json)
    monkeypatch.setattr(keycloak_link_group_role.AnsibleModule, 'fail_json', fail_json)
    arguments = {
        'auth_keycloak_url': 'http://keycloak.url/auth',
        'auth_username': 'test_admin',
        'auth_password': 'admin_password',
        'auth_realm': 'master',
        'realm': 'master',
        'state': 'absent',
        'group_name': 'one_group',
    }
    arguments.update(extra_arguments)

    set_module_args(arguments)
    with pytest.raises(AnsibleExitJson) as exec_trace:
        keycloak_link_group_role.main()
    ansible_exit_json = exec_trace.value.args[0]
    assert not ansible_exit_json['changed']
    assert ansible_exit_json['msg'] == waited_message
    assert ansible_exit_json['roles_in_group'] == {}


@pytest.mark.parametrize('extra_arguments, waited_message', [
    ({'group_name': 'to_link', 'role_name': 'one_role'}, 'Link between to_link and one_role created.'),
    ({'group_name': 'to_link', 'role_name': 'role_to_link_in_client', 'client_id': 'one_client'},
     'Link between to_link and role_to_link_in_client in one_client created.'),
    ({'group_id': 'b180d727-3e8b-476c-95e2-345edd96d853', 'role_id': '7c300837-8221-4196-9e02-1f183bfd1882'},
     'Link between b180d727-3e8b-476c-95e2-345edd96d853 and 7c300837-8221-4196-9e02-1f183bfd1882 created.')
], ids=['with name in realm', 'with name one client', 'with uuid for groups and roles'])
def test_state_present_without_link_should_create_link(monkeypatch, extra_arguments, waited_message):
    monkeypatch.setattr(keycloak_link_group_role.AnsibleModule, 'exit_json', exit_json)
    monkeypatch.setattr(keycloak_link_group_role.AnsibleModule, 'fail_json', fail_json)
    arguments = {
        'auth_keycloak_url': 'http://keycloak.url/auth',
        'auth_username': 'test_admin',
        'auth_password': 'admin_password',
        'auth_realm': 'master',
        'realm': 'master',
        'state': 'present',
    }
    arguments.update(extra_arguments)
    set_module_args(arguments)
    with pytest.raises(AnsibleExitJson) as exec_trace:
        keycloak_link_group_role.main()
    ansible_exit_json = exec_trace.value.args[0]
    assert ansible_exit_json['msg'] == waited_message
    assert ansible_exit_json['changed']
    if 'role_name' in extra_arguments:
        assert ansible_exit_json['roles_in_group']['name'] == extra_arguments['role_name']
    else:
        assert ansible_exit_json['roles_in_group']['id'] == extra_arguments['role_id']


@pytest.mark.parametrize('extra_arguments, waited_message', [
    ({'group_name': 'one_group', 'role_name': 'already_link_role'},
     'Links between one_group and already_link_role exists, doing nothing.'),
    ({'group_name': 'one_group', 'role_name': 'already_link_role', 'client_id': 'one_client'},
     'Links between one_group and already_link_role in one_client exists, doing nothing.')
], ids=['role in master', 'role in client'])
def test_state_present_with_link_should_no_do_something(monkeypatch, extra_arguments, waited_message):
    monkeypatch.setattr(keycloak_link_group_role.AnsibleModule, 'exit_json', exit_json)
    monkeypatch.setattr(keycloak_link_group_role.AnsibleModule, 'fail_json', fail_json)
    arguments = {
        'auth_keycloak_url': 'http://keycloak.url/auth',
        'auth_username': 'test_admin',
        'auth_password': 'admin_password',
        'auth_realm': 'master',
        'realm': 'master',
        'state': 'present',
    }
    arguments.update(extra_arguments)
    set_module_args(arguments)
    with pytest.raises(AnsibleExitJson) as exec_trace:
        keycloak_link_group_role.main()
    ansible_exit_json = exec_trace.value.args[0]
    assert not ansible_exit_json['changed']
    assert ansible_exit_json['msg'] == waited_message
    assert ansible_exit_json['roles_in_group']['name'] == extra_arguments['role_name']


@pytest.mark.parametrize('extra_arguments, waited_message', [
    ({'group_name': 'one_group', 'role_name': 'to_unlink'},
     'Links between one_group and to_unlink deleted.'),
    ({'group_name': 'one_group', 'role_name': 'to_unlink', 'client_id': 'one_client'},
     'Links between one_group and to_unlink in one_client deleted.')
], ids=['role in master', 'role in client'])
def test_state_absent_with_existing_should_delete_the_link(monkeypatch, extra_arguments, waited_message):
    monkeypatch.setattr(keycloak_link_group_role.AnsibleModule, 'exit_json', exit_json)
    monkeypatch.setattr(keycloak_link_group_role.AnsibleModule, 'fail_json', fail_json)
    arguments = {
        'auth_keycloak_url': 'http://keycloak.url/auth',
        'auth_username': 'test_admin',
        'auth_password': 'admin_password',
        'auth_realm': 'master',
        'realm': 'master',
        'state': 'absent',
    }
    arguments.update(extra_arguments)
    set_module_args(arguments)
    with pytest.raises(AnsibleExitJson) as exec_trace:
        keycloak_link_group_role.main()
    ansible_exit_json = exec_trace.value.args[0]
    assert ansible_exit_json['changed']
    assert ansible_exit_json['msg'] == waited_message
    assert not ansible_exit_json['roles_in_group']


@pytest.mark.parametrize('extra_arguments, waited_message', [
    ({'group_name': 'doesnotexist', 'role_name': 'one_role'},
     'group doesnotexist not found.'),
    ({'group_id': '000-000', 'role_name': 'one_role'},
     'group 000-000 not found.'),
    ({'group_name': 'one_group', 'role_name': 'doesnotexist'},
     'role doesnotexist not found.'),
    ({'group_name': 'one_group', 'role_id': '000-000'},
     'role 000-000 not found.'),
    ({'group_name': 'one_group', 'role_name': 'one_role', 'client_id': 'doesnotexist'},
     'client doesnotexist not found.'),
    ({'group_name': 'one_group', 'role_name': 'doesnotexist', 'client_id': 'one_client'},
     'role doesnotexist not found in one_client.'),
], ids=['group name', 'group id', 'role name', 'role id', 'client name',
        'role name in client'])
def test_with_wrong_parameters(monkeypatch, extra_arguments, waited_message):
    monkeypatch.setattr(keycloak_link_group_role.AnsibleModule, 'exit_json', exit_json)
    monkeypatch.setattr(keycloak_link_group_role.AnsibleModule, 'fail_json', fail_json)
    arguments = {
        'auth_keycloak_url': 'http://keycloak.url/auth',
        'auth_username': 'test_admin',
        'auth_password': 'admin_password',
        'auth_realm': 'master',
        'realm': 'master',
        'state': 'absent',
    }
    arguments.update(extra_arguments)
    set_module_args(arguments)
    with pytest.raises(AnsibleFailJson) as exec_trace:
        keycloak_link_group_role.main()
    ansible_exit_json = exec_trace.value.args[0]
    assert ansible_exit_json['msg'] == waited_message