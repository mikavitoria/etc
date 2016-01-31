# -*- coding: utf-8 -*-
"""
   etc.adapters
   ~~~~~~~~~~~~
"""
from __future__ import absolute_import

import io
from urlparse import urljoin

import requests

from .results import DirectoryNode, Node, Result, ValueNode


__all__ = ['Adapter', 'EtcdAdapter']


class Adapter(object):
    """An interface to implement several essential raw methods of etcd."""

    def get(self, key, recursive=False, sorted=False, quorum=False,
            wait=False, wait_index=0, timeout=None):
        raise NotImplementedError

    def set(self, key, value=None, dir=False, ttl=None,
            prev_value=None, prev_index=None, prev_exist=None, timeout=None):
        raise NotImplementedError

    def append(self, key, value=None, dir=False, ttl=None, timeout=None):
        raise NotImplementedError

    def delete(self, key, dir=False, recursive=False,
               prev_value=None, prev_index=None, timeout=None):
        raise NotImplementedError


class EtcdAdapter(Adapter):
    """An adapter which communicates with an etcd v2 server."""

    def __init__(self, url=u'http://127.0.0.1:4001', default_timeout=60):
        self.url = url
        self.default_timeout = default_timeout
        self.session = requests.Session()

    def make_url(self, path, api_root=u'/v2/'):
        """Gets a full URL from just path."""
        return urljoin(urljoin(self.url, api_root), path)

    def make_key_url(self, key):
        """Gets a URL for a key."""
        if type(key) is bytes:
            key = key.decode('utf-8')
        buf = io.StringIO()
        buf.write(u'keys')
        if not key.startswith(u'/'):
            buf.write(u'/')
        buf.write(key)
        return self.make_url(buf.getvalue())

    @classmethod
    def make_node(cls, data):
        key = data['key']
        kwargs = {
            'modified_index': data['modifiedIndex'],
            'created_index': data['createdIndex'],
        }
        ttl = data.get('ttl')
        if ttl is not None:
            kwargs.update(ttl=ttl, expiration=data['expiration'])
        if 'value' in data:
            cls = ValueNode
            args = (data['value'],)
        elif data.get('dir', False):
            cls = DirectoryNode
            args = ([cls.make_node(n) for n in data.get('nodes', ())],)
        else:
            cls, args = Node, ()
        return cls(key, *args, **kwargs)

    @classmethod
    def make_result(cls, data, headers=None):
        action = data['action']
        node = cls.make_node(data['node'])
        kwargs = {}
        try:
            prev_node_data = data['prev_node']
        except KeyError:
            pass
        else:
            kwargs['prev_node'] = cls.make_node(prev_node_data)
        if headers:
            kwargs.update(etcd_index=int(headers['X-Etcd-Index']),
                          raft_index=int(headers['X-Raft-Index']),
                          raft_term=int(headers['X-Raft-Term']))
        return Result.make(action, node, **kwargs)

    @classmethod
    def wrap_response(cls, res):
        print res.json()
        if res.ok:
            return cls.make_result(res.json(), res.headers)

    @staticmethod
    def build_args(args=None, **kwargs):
        if args is None:
            args = {}
        for key, (type_, value) in kwargs.items():
            if value is None:
                continue
            if type_ is bool:
                args[key] = u'true' if value else u'false'
            else:
                args[key] = value
        return args

    def get(self, key, recursive=False, sorted=False, quorum=False,
            wait=False, wait_index=0, timeout=None):
        """Requests to get a node by the given key."""
        url = self.make_key_url(key)
        params = self.build_args(recursive=(bool, recursive or None),
                                 sorted=(bool, sorted or None),
                                 quorum=(bool, quorum or None),
                                 wait=(bool, wait or None),
                                 wait_index=(int, wait_index))
        with self.session as s:
            res = s.get(url, params=params, timeout=timeout)
        return self.wrap_response(res)

    def set(self, key, value=None, dir=False, ttl=None,
            prev_value=None, prev_index=None, prev_exist=None, timeout=None):
        """Requests to create an ordered node into a node by the given key."""
        if (value is None) == (not dir):
            raise ValueError('Set value or make as directory')
        if value is not None and not isinstance(value, unicode):
            raise TypeError('Set unicode value')
        url = self.make_key_url(key)
        data = self.build_args(value=(unicode, value),
                               dir=(bool, dir or None),
                               ttl=(int, ttl),
                               prev_value=(unicode, prev_value),
                               prev_index=(int, prev_index),
                               prev_exist=(bool, prev_exist))
        with self.session as s:
            res = s.put(url, data=data, timeout=timeout)
        return self.wrap_response(res)

    def append(self, key, value=None, dir=False, ttl=None, timeout=None):
        """Requests to create an ordered node into a node by the given key."""
        if (value is None) == (not dir):
            raise ValueError('Set value or make as directory')
        if value is not None and not isinstance(value, unicode):
            raise TypeError('Set unicode value')
        url = self.make_key_url(key)
        data = self.build_args(value=(unicode, value),
                               dir=(bool, dir or None),
                               ttl=(int, ttl))
        with self.session as s:
            res = s.post(url, data=data, timeout=timeout)
        return self.wrap_response(res)

    def delete(self, key, dir=False, recursive=False,
               prev_value=None, prev_index=None, timeout=None):
        """Requests to delete a node by the given key."""
        url = self.make_key_url(key)
        data = self.build_args(dir=(bool, dir or None),
                               recursive=(bool, recursive or None),
                               prev_value=(unicode, prev_value),
                               prev_index=(int, prev_index))
        with self.session as s:
            res = s.delete(url, data=data, timeout=timeout)
        return self.wrap_response(res)