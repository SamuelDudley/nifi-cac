"""Reusable flow blocks.

A block is a function that builds a child process group with named ports.
Call it twice with different names and you get two independent instances that
share one definition.

Block contract:
  - takes a parent :class:`~nificac.build.Group` and an instance name
  - returns the child ``Group``
  - exposes ports through ``group.inputs[...]`` and ``group.outputs[...]``
  - documents every port in its docstring
"""

from __future__ import annotations

from .build import AWS, STANDARD, Group

PUT_S3_OBJECT = "org.apache.nifi.processors.aws.s3.PutS3Object"
LOG_ATTRIBUTE = "org.apache.nifi.processors.standard.LogAttribute"


def s3_sink(
    parent: Group,
    name: str,
    *,
    bucket: str,
    key: str,
    credentials: str,
    region: str,
) -> Group:
    """Write flow file content to S3.

    Ports:
      in       (input)  flow files to write
      failure  (output) flow files S3 rejected
    """
    group = parent.block(name)
    source = group.port("in", "INPUT_PORT")
    failure = group.port("failure", "OUTPUT_PORT")
    put = group.processor(
        "OUT_PutS3Object",
        PUT_S3_OBJECT,
        AWS,
        properties={
            "Bucket": bucket,
            "Object Key": key,
            "Region": region,
            "AWS Credentials Provider service": credentials,
        },
        auto_terminate=["success"],
    )
    group.connect(source, put)
    group.connect(put, failure, "failure")
    return group


def log_sink(parent: Group, name: str, *, level: str = "error") -> Group:
    """Log the attributes of a flow file, then discard it.

    Ports:
      in  (input)  flow files to log
    """
    group = parent.block(name)
    source = group.port("in", "INPUT_PORT")
    log = group.processor(
        "ERR_LogAttribute",
        LOG_ATTRIBUTE,
        STANDARD,
        properties={"Log Level": level, "Log Payload": "false"},
        auto_terminate=["success"],
    )
    group.connect(source, log)
    return group
