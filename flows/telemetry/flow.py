"""SQS event -> fetch S3 object -> extract content -> Lambda -> write S3.

Failures from every stage fan into one funnel and land in a dead letter
bucket. The S3 write is one block, instantiated twice.
"""

from nificac.blocks import log_sink, s3_sink
from nificac.build import AWS, STANDARD, Group, sid
from nificac.models import (
    RegisteredFlowSnapshot,
    VersionedParameter,
    VersionedParameterContext,
)

GET_SQS = "org.apache.nifi.processors.aws.sqs.GetSQS"
FETCH_S3_OBJECT = "org.apache.nifi.processors.aws.s3.FetchS3Object"
PUT_LAMBDA = "org.apache.nifi.processors.aws.lambda.PutLambda"
EVALUATE_JSON_PATH = "org.apache.nifi.processors.standard.EvaluateJsonPath"
AWS_CREDENTIALS = (
    "org.apache.nifi.processors.aws.credentials.provider.service"
    ".AWSCredentialsProviderControllerService"
)

REGION = "#{aws.region}"
ROOT = "telemetry"


def build() -> RegisteredFlowSnapshot:
    root = Group(ROOT, "Telemetry Enrichment")

    credentials = root.service(
        "CS_AwsCredentials",
        AWS_CREDENTIALS,
        AWS,
        {
            "Access Key ID": "#{aws.access.key.id}",
            "Secret Access Key": "#{aws.secret.access.key}",
        },
    )
    aws_common = {
        "Region": REGION,
        "AWS Credentials Provider service": credentials.identifier,
    }

    # 1. Wait on the queue.
    sqs = root.processor(
        "IN_GetSQS",
        GET_SQS,
        AWS,
        {
            **aws_common,
            "Queue URL": "#{sqs.queue.url}",
            "Batch Size": "10",
            "Receive Message Wait Time": "20 secs",
            "Auto Delete Messages": "true",
        },
        scheduling_period="0 sec",
    )

    # 2. Read the bucket and the key out of the S3 event notification.
    parse = root.processor(
        "PRC_ParseS3Event",
        EVALUATE_JSON_PATH,
        STANDARD,
        {
            "Destination": "flowfile-attribute",
            "Return Type": "json",
            "s3.bucket": "$.Records[0].s3.bucket.name",
            "s3.key": "$.Records[0].s3.object.key",
        },
    )

    # 3. Fetch the object. S3 event keys are URL encoded, so decode inline.
    fetch = root.processor(
        "PRC_FetchS3Object",
        FETCH_S3_OBJECT,
        AWS,
        {
            **aws_common,
            "Bucket": "${s3.bucket}",
            "Object Key": "${s3.key:urlDecode()}",
        },
    )

    # 4. Replace the flow file content with the payload field.
    extract = root.processor(
        "PRC_ExtractContent",
        EVALUATE_JSON_PATH,
        STANDARD,
        {
            "Destination": "flowfile-content",
            "Return Type": "json",
            "content": "$.payload",
        },
    )

    # 5. Post to Lambda. The function response becomes the flow file content.
    invoke = root.processor(
        "PRC_InvokeLambda",
        PUT_LAMBDA,
        AWS,
        {
            **aws_common,
            "Amazon Lambda Name": "#{lambda.function.name}",
            "Amazon Lambda Qualifier": "$LATEST",
        },
    )

    # 6. One block, two instances.
    results = s3_sink(
        root,
        "OUT_Results",
        bucket="#{s3.output.bucket}",
        key="enriched/${filename}",
        credentials=credentials.identifier,
        region=REGION,
    )
    dead_letter = s3_sink(
        root,
        "ERR_DeadLetter",
        bucket="#{s3.deadletter.bucket}",
        key="failed/${uuid}",
        credentials=credentials.identifier,
        region=REGION,
    )
    unwritable = log_sink(root, "ERR_Unwritable")

    root.connect(sqs, parse, "success")
    root.connect(parse, fetch, "matched")
    root.connect(fetch, extract, "success")
    root.connect(extract, invoke, "matched")
    root.connect(invoke, results.inputs["in"], "success")

    errors = root.funnel("ERR_Fanin")
    for processor, relationship in (
        (parse, "unmatched"),
        (parse, "failure"),
        (fetch, "failure"),
        (extract, "unmatched"),
        (extract, "failure"),
        (invoke, "failure"),
    ):
        root.connect(processor, errors, relationship)
    root.connect(results.outputs["failure"], errors)
    root.connect(errors, dead_letter.inputs["in"])

    # The dead letter failure must not return to the funnel. That is a cycle,
    # and the flow file would loop until it expires.
    root.connect(dead_letter.outputs["failure"], unwritable.inputs["in"])

    return RegisteredFlowSnapshot(
        flow_contents=root.build(),
        parameter_contexts={
            "telemetry": VersionedParameterContext(
                identifier=sid(f"{ROOT}/parameter-context"),
                name="telemetry",
                component_type="PARAMETER_CONTEXT",
                parameters=[
                    VersionedParameter(name="aws.region", value="eu-west-2"),
                    VersionedParameter(name="sqs.queue.url"),
                    VersionedParameter(name="lambda.function.name"),
                    VersionedParameter(name="s3.output.bucket"),
                    VersionedParameter(name="s3.deadletter.bucket"),
                    VersionedParameter(name="aws.access.key.id", sensitive=True),
                    VersionedParameter(name="aws.secret.access.key", sensitive=True),
                ],
            )
        },
    )
