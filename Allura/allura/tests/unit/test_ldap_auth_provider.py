# -*- coding: utf-8 -*-

#       Licensed to the Apache Software Foundation (ASF) under one
#       or more contributor license agreements.  See the NOTICE file
#       distributed with this work for additional information
#       regarding copyright ownership.  The ASF licenses this file
#       to you under the Apache License, Version 2.0 (the
#       "License"); you may not use this file except in compliance
#       with the License.  You may obtain a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#       Unless required by applicable law or agreed to in writing,
#       software distributed under the License is distributed on an
#       "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
#       KIND, either express or implied.  See the License for the
#       specific language governing permissions and limitations
#       under the License.

from mock import patch, Mock
from nose.tools import assert_equal, assert_not_equal, assert_true
from webob import Request
from ming.orm.ormsession import ThreadLocalORMSession
from tg import config

from alluratest.controller import setup_basic_test
from allura.lib import plugin
from allura.lib import helpers as h
from allura import model as M


class TestLdapAuthenticationProvider(object):

    def setUp(self):
        setup_basic_test()
        self.provider = plugin.LdapAuthenticationProvider(Request.blank('/'))

    def test_password_encoder(self):
        # Verify salt
        ep = self.provider._encode_password
        assert_not_equal(ep('test_pass'), ep('test_pass'))
        assert_equal(ep('test_pass', '0000'), ep('test_pass', '0000'))
        # Test password format
        assert_true(ep('pwd').startswith('{CRYPT}$6$rounds=6000$'))

    @patch('allura.lib.plugin.ldap')
    def test_set_password(self, ldap):
        user = Mock(username='test-user')
        self.provider._encode_password = Mock(return_value='new-pass-hash')
        ldap.dn.escape_dn_chars = lambda x: x

        dn = 'uid=%s,ou=users,dc=sf,dc=net' % user.username
        self.provider.set_password(user, 'old-pass', 'new-pass')
        ldap.initialize.assert_called_once_with('ldaps://localhost/')
        connection = ldap.initialize.return_value
        connection.bind_s.called_once_with(dn, 'old-pass')
        connection.modify_s.assert_called_once_with(
            dn, [(ldap.MOD_REPLACE, 'userPassword', 'new-pass-hash')])
        connection.unbind_s.assert_called_once()

    @patch('allura.lib.plugin.ldap')
    def test_login(self, ldap):
        params = {
            'username': 'test-user',
            'password': 'test-password',
        }
        self.provider.request.method = 'POST'
        self.provider.request.body = '&'.join(['%s=%s' % (k,v) for k,v in params.iteritems()])
        ldap.dn.escape_dn_chars = lambda x: x

        dn = 'uid=%s,ou=users,dc=sf,dc=net' % params['username']
        self.provider._login()
        ldap.initialize.assert_called_once_with('ldaps://localhost/')
        connection = ldap.initialize.return_value
        connection.bind_s.called_once_with(dn, 'test-password')
        connection.unbind_s.assert_called_once()

    @patch('allura.lib.plugin.modlist')
    @patch('allura.lib.plugin.ldap')
    def test_register_user(self, ldap, modlist):
        user_doc = {
            'username': u'new-user',
            'display_name': u'New User',
            'password': u'new-password',
        }
        ldap.dn.escape_dn_chars = lambda x: x
        self.provider._encode_password = Mock(return_value='new-password-hash')

        assert_equal(M.User.query.get(username=user_doc['username']), None)
        with h.push_config(config, **{'auth.ldap.autoregister': 'false'}):
            self.provider.register_user(user_doc)
        ThreadLocalORMSession.flush_all()
        assert_not_equal(M.User.query.get(username=user_doc['username']), None)

        dn = 'uid=%s,ou=users,dc=sf,dc=net' % user_doc['username']
        ldap.initialize.assert_called_once_with('ldaps://localhost/')
        connection = ldap.initialize.return_value
        connection.bind_s.called_once_with(
            'cn=site,ou=admin,dc=sf,dc=net',
            'admin-password')
        connection.add_s.assert_called_once_with(dn, modlist.addModlist.return_value)
        connection.unbind_s.assert_called_once()