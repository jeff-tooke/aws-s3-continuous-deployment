import boto3
import os

def lambda_handler(event, context):
    boto3.client('codebuild').start_build(
    projectName= os.environ['BUILD_PROJECT_NAME']
)