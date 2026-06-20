# Copyright (c) Meta Platforms, Inc. and affiliates.

# pyre-unsafe

from thrift.py3.serializer import Protocol, serialize


def thrift_to_json(thrift_object):
    return serialize(thrift_object, protocol=Protocol.JSON).decode("utf-8")
