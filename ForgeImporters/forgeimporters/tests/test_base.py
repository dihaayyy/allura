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

from unittest import TestCase

from formencode import Invalid
import mock
from tg import expose
from nose.tools import assert_equal, assert_raises
from webob.exc import HTTPUnauthorized

from alluratest.controller import TestController
from allura.tests import decorators as td

from .. import base


class TestProjectExtractor(TestCase):
    @mock.patch('forgeimporters.base.h.urlopen')
    @mock.patch('forgeimporters.base.urllib2.Request')
    def test_urlopen(self, Request, urlopen):
        r = base.ProjectExtractor.urlopen('myurl', data='foo')
        Request.assert_called_once_with('myurl', data='foo')
        req = Request.return_value
        req.add_header.assert_called_once_with(
                'User-Agent', 'Allura Data Importer (https://forge-allura.apache.org/p/allura/)')
        urlopen.assert_called_once_with(req, retries=3, codes=(408,))
        self.assertEqual(r, urlopen.return_value)


@mock.patch.object(base.ToolImporter, 'by_name')
@mock.patch.object(base, 'c')
@mock.patch.object(base, 'g')
def test_import_tool(g, c, by_name):
    c.project = mock.Mock(name='project')
    c.user = mock.Mock(name='user')
    base.import_tool('importer_name', project_name='project_name',
            mount_point='mount_point', mount_label='mount_label')
    by_name.assert_called_once_with('importer_name')
    by_name.return_value.import_tool.assert_called_once_with(c.project,
            c.user, project_name='project_name', mount_point='mount_point',
            mount_label='mount_label')
    assert not g.post_event.called


@mock.patch.object(base.traceback, 'format_exc')
@mock.patch.object(base, 'ToolImporter')
@mock.patch.object(base, 'g')
def test_import_tool_failed(g, ToolImporter, format_exc):
    format_exc.return_value = 'my traceback'

    importer = mock.Mock(source='importer_source',
            tool_label='importer_tool_label')
    importer.import_tool.side_effect = RuntimeError('my error')
    ToolImporter.by_name.return_value = importer

    assert_raises(RuntimeError, base.import_tool, 'importer_name',
            project_name='project_name')
    g.post_event.assert_called_once_with(
            'import_tool_task_failed',
            error=str(importer.import_tool.side_effect),
            traceback='my traceback',
            importer_source='importer_source',
            importer_tool_label='importer_tool_label',
            project_name='project_name',
        )


def ep(name, source=None, importer=None, **kw):
    mep = mock.Mock(name='mock_ep', **kw)
    mep.name = name
    if importer is not None:
        mep.load.return_value = importer
    else:
        mep.load.return_value.source = source
        mep.lv = mep.load.return_value.return_value
        mep.lv.source = source
    return mep


class TestProjectImporter(TestCase):
    @mock.patch.object(base.h, 'iter_entry_points')
    def test_tool_importers(self, iep):
        eps = iep.return_value = [ep('ep1', 'foo'), ep('ep2', 'bar'), ep('ep3', 'foo')]
        pi = base.ProjectImporter(mock.Mock(name='neighborhood'))
        pi.source = 'foo'
        self.assertEqual(pi.tool_importers, {'ep1': eps[0].lv, 'ep3': eps[2].lv})
        iep.assert_called_once_with('allura.importers')

    @mock.patch.object(base, 'redirect')
    @mock.patch.object(base, 'flash')
    @mock.patch.object(base, 'import_tool')
    @mock.patch.object(base, 'M')
    @mock.patch.object(base, 'c')
    def test_process(self, c, M, import_tool, flash, redirect):
        pi = base.ProjectImporter(mock.Mock())
        pi.source = 'Source'
        pi.after_project_create = mock.Mock()
        pi.neighborhood.register_project.return_value.script_name = 'script_name/'
        kw = {
                'project_name': 'project_name',
                'project_shortname': 'shortname',
                'tools': ['tool'],
            }
        with mock.patch.dict(base.config, {'site_name': 'foo'}):
            pi.process(**kw)
        pi.neighborhood.register_project.assert_called_once_with('shortname', project_name='project_name')
        pi.after_project_create.assert_called_once_with(c.project, **kw)
        import_tool.post.assert_called_once_with('tool', **kw)
        M.AuditLog.log.assert_called_once_with('import project from Source')
        self.assertEqual(flash.call_count, 1)
        redirect.assert_called_once_with('script_name/admin/overview')

    @mock.patch.object(base.h, 'request')
    @mock.patch.object(base, 'require_access')
    @mock.patch.object(base.h, 'c')
    def test_login_overlay(self, c, require_access, request):
        pi = base.ProjectImporter(mock.Mock())
        require_access.side_effect = HTTPUnauthorized

        c.show_login_overlay = False
        request.path = '/test-importer/'
        pi._check_security()
        self.assertEqual(c.show_login_overlay, True)

        c.show_login_overlay = False
        request.path = '/test-importer/check_names/'
        pi._check_security()
        self.assertEqual(c.show_login_overlay, True)

        c.show_login_overlay = False
        request.path = '/test-importer/process/'
        with td.raises(HTTPUnauthorized):
            pi._check_security()
        self.assertEqual(c.show_login_overlay, False)



TA1 = mock.Mock(tool_label='foo', tool_description='foo_desc')
TA2 = mock.Mock(tool_label='qux', tool_description='qux_desc')
TA3 = mock.Mock(tool_label='baz', tool_description='baz_desc')

class TI1Controller(object):
    @expose()
    def index(self, *a, **kw):
        return 'test importer 1 controller webpage'

class TI1(base.ToolImporter):
    target_app = TA1
    controller = TI1Controller

class TI2(base.ToolImporter):
    target_app = TA2
    tool_label = 'bar'
    tool_description = 'bar_desc'

class TI3(base.ToolImporter):
    target_app = [TA2, TA2]

class TestToolImporter(TestCase):


    @mock.patch.object(base.h, 'iter_entry_points')
    def test_by_name(self, iep):
        eps = iep.return_value = [ep('my-name', 'my-source')]
        importer = base.ToolImporter.by_name('my-name')
        iep.assert_called_once_with('allura.importers', 'my-name')
        self.assertEqual(importer, eps[0].lv)

        iep.reset_mock()
        iep.return_value = []
        importer = base.ToolImporter.by_name('other-name')
        iep.assert_called_once_with('allura.importers', 'other-name')
        self.assertEqual(importer, None)

    @mock.patch.object(base.h, 'iter_entry_points')
    def test_by_app(self, iep):
        eps = iep.return_value = [
                ep('importer1', importer=TI1),
                ep('importer2', importer=TI2),
                ep('importer3', importer=TI3),
            ]
        importers = base.ToolImporter.by_app(TA2)
        self.assertEqual(set(importers.keys()), set([
                'importer2',
                'importer3',
            ]))
        self.assertIsInstance(importers['importer2'], TI2)
        self.assertIsInstance(importers['importer3'], TI3)

    def test_tool_label(self):
        self.assertEqual(TI1().tool_label, 'foo')
        self.assertEqual(TI2().tool_label, 'bar')
        self.assertEqual(TI3().tool_label, 'qux')

    def test_tool_description(self):
        self.assertEqual(TI1().tool_description, 'foo_desc')
        self.assertEqual(TI2().tool_description, 'bar_desc')
        self.assertEqual(TI3().tool_description, 'qux_desc')


class TestToolsValidator(TestCase):
    def setUp(self):
        self.tv = base.ToolsValidator('good-source')

    @mock.patch.object(base.ToolImporter, 'by_name')
    def test_empty(self, by_name):
        self.assertEqual(self.tv.to_python(''), [])
        self.assertEqual(by_name.call_count, 0)

    @mock.patch.object(base.ToolImporter, 'by_name')
    def test_no_ep(self, by_name):
        eps = by_name.return_value = None
        with self.assertRaises(Invalid) as cm:
            self.tv.to_python('my-value')
        self.assertEqual(cm.exception.msg, 'Invalid tool selected: my-value')
        by_name.assert_called_once_with('my-value')

    @mock.patch.object(base.ToolImporter, 'by_name')
    def test_bad_source(self, by_name):
        eps = by_name.return_value = ep('ep1', 'bad-source').lv
        with self.assertRaises(Invalid) as cm:
            self.tv.to_python('my-value')
        self.assertEqual(cm.exception.msg, 'Invalid tool selected: my-value')
        by_name.assert_called_once_with('my-value')

    @mock.patch.object(base.ToolImporter, 'by_name')
    def test_multiple(self, by_name):
        eps = by_name.side_effect = [ep('ep1', 'bad-source').lv, ep('ep2', 'good-source').lv, ep('ep3', 'bad-source').lv]
        with self.assertRaises(Invalid) as cm:
            self.tv.to_python(['value1', 'value2', 'value3'])
        self.assertEqual(cm.exception.msg, 'Invalid tools selected: value1, value3')
        self.assertEqual(by_name.call_args_list, [
                mock.call('value1'),
                mock.call('value2'),
                mock.call('value3'),
            ])

    @mock.patch.object(base.ToolImporter, 'by_name')
    def test_valid(self, by_name):
        eps = by_name.side_effect = [ep('ep1', 'good-source').lv, ep('ep2', 'good-source').lv, ep('ep3', 'bad-source').lv]
        self.assertEqual(self.tv.to_python(['value1', 'value2']), ['value1', 'value2'])
        self.assertEqual(by_name.call_args_list, [
                mock.call('value1'),
                mock.call('value2'),
            ])


class TestProjectToolsImportController(TestController):

    def test_pages(self):
        admin_page = self.app.get('/admin/')
        with mock.patch.object(base.h, 'iter_entry_points') as iep:
            iep.return_value = [
                ep('importer1', importer=TI1),
                ep('importer2', importer=TI2),
                ep('importer3', importer=TI3),
            ]
            import_main_page = admin_page.click('Import')
        url = import_main_page.environ['PATH_INFO']
        assert url.endswith('/admin/ext/import/'), url

        with mock.patch.object(base.ToolImporter, 'by_name') as by_name:
            by_name.return_value = TI1
            import1_page = import_main_page.click('Import', href=r'importer1$')
        url = import1_page.environ['PATH_INFO']
        assert url.endswith('/admin/ext/import/importer1'), url
        assert_equal(import1_page.body, 'test importer 1 controller webpage')
