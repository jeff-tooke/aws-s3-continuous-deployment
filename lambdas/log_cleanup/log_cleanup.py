import boto3
import os

def lambda_handler(event, context):
    logs = boto3.client('logs')
    log_groups = [os.environ['BUILD_LOG'], os.environ['TRIGGER_LOG'], os.environ['CDN_INVALIDATION_LOG']]
    for log_group in log_groups:
            logs.delete_log_group(
                logGroupName= log_group
    )