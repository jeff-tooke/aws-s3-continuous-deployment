#!/usr/bin/env python3
from pathlib import Path
import os
import glob
import zipfile
import time
import datetime
import json
import boto3
import settings as var
#boto3.set_stream_logger('')

##########################################
# Create S3 bucket
##########################################
print()
print('Creating S3 bucket...')
s3 = boto3.client('s3')
s3.create_bucket(
    Bucket= var.website_fqdn,
    ACL = 'public-read',
    CreateBucketConfiguration = {
    'LocationConstraint': var.region
}
)
s3.put_bucket_tagging(
    Bucket= var.website_fqdn,
    Tagging={
        'TagSet':[
            {
              'Key': 'Name',
              'Value': var.proj_name
            },
        ]
    }
)
s3.put_bucket_website(
    Bucket= var.website_fqdn,
    WebsiteConfiguration={
        'ErrorDocument': {
            'Key': 'error.html'
        },
        'IndexDocument': {
            'Suffix': 'index.html'
        }
    }
)
bucket_arn = 'arn:aws:s3:::'+var.website_fqdn
print()
###########################################
## Update s3 bucket policy
###########################################
print('Updating s3 bucket policy...')
bucket_policy = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "CodeBuildPushFromSCM",
            "Effect": "Allow",
            "Principal": {
                "Service": "codebuild.amazonaws.com"
            },
            "Action": [
                "s3:PutObject",
                "s3:ListBucket",
                "s3:GetObject",
                "s3:GetObjectVersion"
            ],
            "Resource": [
                bucket_arn,
                bucket_arn+'/*'
            ]
        },
        {
            "Sid": "AllowPublicRead",
            "Effect": "Allow",
            "Principal": '*',
            "Action": "s3:GetObject",
            "Resource": bucket_arn+'/*'
        }
    ]
}
bucket_policy = json.dumps(bucket_policy)
s3.put_bucket_policy(Bucket= var.website_fqdn, Policy=bucket_policy)
time.sleep(5)
print()
##########################################
# Create Codecommit Repository
##########################################
print('Creating repository...')
create_repo = boto3.client('codecommit').create_repository(
    repositoryName= var.proj_name,
    repositoryDescription= 'Software repository for '+var.proj_desc
)
http_repo_url = create_repo['repositoryMetadata']['cloneUrlHttp']
ssh_repo_url = create_repo['repositoryMetadata']['cloneUrlSsh']
repo_arn= create_repo['repositoryMetadata']['Arn']
print()
################################################
# Set permissions for Codebuild project
################################################
print('Creating role for build...')
build_policy = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": "codecommit:GitPull",
            "Resource": repo_arn
        },
        {
            "Effect": "Allow",
            "Action": [
                "s3:PutObject",
                "s3:GetObject",
                "s3:ListBucket",
                "s3:GetObjectVersion"
            ],
            "Resource": bucket_arn+"*"
        },
        {
            "Effect": "Allow",
            "Action": [
                "logs:CreateLogGroup",
                "logs:CreateLogStream",
                "logs:PutLogEvents"
            ],
            "Resource": '*'
        }
    ]
}
build_policy = json.dumps(build_policy)
iam = boto3.client('iam')
create_build_policy = iam.create_policy(
    PolicyName= var.proj_name+'-codebuild-policy',
    Path= '/'+var.proj_name+'/codebuild/',
    PolicyDocument= build_policy,
    Description= 'Policy attached to codebuild. Part of '+var.proj_desc
)
build_policy_arn = create_build_policy['Policy']['Arn']
assume_role_policy = {
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "codebuild.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
assume_role_policy = json.dumps(assume_role_policy)
create_build_role = iam.create_role(
    RoleName= var.proj_name+'-codebuild-role',
    Path= '/'+var.proj_name+'/codebuild/',
    AssumeRolePolicyDocument= assume_role_policy,
    Description= 'Codebuild service execution role. Part of '+var.proj_desc
)
iam.attach_role_policy(
    RoleName= create_build_role['Role']['RoleName'],
    PolicyArn= build_policy_arn
)
build_role_arn = create_build_role['Role']['Arn']
time.sleep(30)
print()
################################################
# Create Build project
################################################
print('Creating build project...')
create_build_project = boto3.client('codebuild').create_project(
    name= var.proj_name,
    description= 'Build steps of '+var.proj_desc,
    source= {
        'type': 'CODECOMMIT',
        'location': http_repo_url,
        'gitCloneDepth': 1,        
    },
    artifacts={
        'type': 'NO_ARTIFACTS'
    },
    environment={
        'type': 'LINUX_CONTAINER',
        'image': 'aws/codebuild/python:latest',
        'computeType': 'BUILD_GENERAL1_SMALL'
    },
    logsConfig={
        'cloudWatchLogs': {
            'status': 'ENABLED'
        }
    },
    serviceRole= build_role_arn
)
build_project_arn = create_build_project['project']['arn']
print()
################################################
#  Set permissions for lambda trigger
###############################################
print('Creating role for lambda build trigger...')
build_trigger_policy = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": "codecommit:GitPull",
            "Resource": repo_arn
        },
        {
            "Effect": "Allow",
            "Action": "codebuild:StartBuild",
            "Resource": build_project_arn
        },
        {
            "Effect": "Allow",
            "Action": [
                "logs:CreateLogGroup",
                "logs:CreateLogStream",
                "logs:PutLogEvents"
            ],
            "Resource": '*'
        }
    ]
}
build_trigger_policy = json.dumps(build_trigger_policy)
iam = boto3.client('iam')
create_trigger_policy = iam.create_policy(
    PolicyName= var.proj_name+'-lambda-build-trigger-policy',
    Path= '/'+var.proj_name+'/lambda/trigger/',
    PolicyDocument= build_trigger_policy,
    Description= 'Policy attached to lambda. Part of '+var.proj_desc
)
assume_role_policy = {
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
assume_role_policy = json.dumps(assume_role_policy)
create_trigger_role = iam.create_role(
    RoleName= var.proj_name+'-lambda-build-trigger-role',
    Path= '/'+var.proj_name+'/lambda/trigger/',
    AssumeRolePolicyDocument= assume_role_policy,
    Description= 'Lambda role to trigger build. Part of '+var.proj_desc
)
iam.attach_role_policy(
    RoleName= create_trigger_role['Role']['RoleName'],
    PolicyArn= create_trigger_policy['Policy']['Arn']
)
time.sleep(30)
print()
################################################
# Create lambda trigger
################################################
print('Creating lambda function to trigger build...')
# zip lambda code for upload
zf = zipfile.ZipFile('build_trigger.zip', 'w')
for name in glob.glob('lambdas/build_trigger/*.py'):
    zf.write(name, os.path.basename(name), zipfile.ZIP_DEFLATED)
zf.close()
# Create lambda
serverless = boto3.client('lambda')
with open('build_trigger.zip', 'rb') as zip_blob:
    create_trigger_function = serverless.create_function(
        FunctionName= var.proj_name+'-build-phase-trigger',
        Runtime= 'python3.6',
        Role= create_trigger_role['Role']['Arn'],
        Handler= 'build_trigger.lambda_handler',
        Code={
            'ZipFile': zip_blob.read()
        },
        Environment={
            'Variables': {
                'BUILD_PROJECT_NAME': var.proj_name
            }
        },
        Timeout= 30,
        Description= 'Trigger build function. Part of '+var.proj_desc,
        Tags={
            'Name': var.proj_name
        },
        Publish= True
)
lambda_policy = serverless.add_permission(
    FunctionName= var.proj_name+'-build-phase-trigger',
    StatementId= 'enable-codecommit-to-invoke-function',
    Action= 'lambda:InvokeFunction',
    Principal= 'codecommit.amazonaws.com',
    SourceArn= repo_arn
)
print()
#################################################
## Create repo trigger
#################################################
boto3.client('codecommit').put_repository_triggers(
    repositoryName= var.proj_name,
    triggers= [
        {
            'name': var.proj_name+'-trigger',
            'destinationArn': create_trigger_function['FunctionArn'],
            'branches': [
                'master',
            ],
            'events': [
                'all'
            ]
        }
    ]
)
##########################################
# Request SSL certificate
##########################################
print('Request ssl certificate for '+var.website_fqdn+'...')
acm = boto3.client('acm', region_name='us-east-1')
cert = acm.request_certificate(
        DomainName= var.website_fqdn,
        ValidationMethod= 'DNS'
        )
time.sleep(5)
acm.add_tags_to_certificate(
    CertificateArn= cert['CertificateArn'],
    Tags=[
        {
            'Key': 'Name',
            'Value': var.proj_name
        },
    ]
)
time.sleep(5)
domain_validation = acm.describe_certificate(
    CertificateArn= cert['CertificateArn']
)
rr_name = domain_validation['Certificate']['DomainValidationOptions'][0]['ResourceRecord']['Name']
rr_value = domain_validation['Certificate']['DomainValidationOptions'][0]['ResourceRecord']['Value']
r53 = boto3.client('route53')
hosted_zone = r53.list_hosted_zones_by_name(
    DNSName= var.dns_domain
)
zone_id = hosted_zone['HostedZones'][0]['Id'][-14:]
r53.change_resource_record_sets(
    HostedZoneId= zone_id,
    ChangeBatch= {
    'Comment': 'Validate ownership of DNS domain',
    'Changes': [
        {
            'Action': 'UPSERT',
                    'ResourceRecordSet': {
                            'Name': rr_name,
                            'ResourceRecords': [
                                {
                                    'Value': rr_value
                                },
                            ],
                            'Type': 'CNAME',
                            'TTL': 300
                    }
            },
        ]
    }
)
print()
print('Wait for certificate to be issued before proceeding...')
time.sleep(120)
print()
input('Press enter to continue...')
print()
##########################################
# Create cloudfront cdn
##########################################
print('Creating cdn for '+var.website_fqdn+'...')
dt = datetime.datetime.now()
call_ref = dt.strftime('%d/%m/%Y %H:%M:%S')
cdn = boto3.client('cloudfront')
create_cdn = cdn.create_distribution_with_tags(
    DistributionConfigWithTags={
        'DistributionConfig': {
            'CallerReference': call_ref,
            'Aliases': {
                'Quantity': 1,
                'Items': [
                    var.website_fqdn,
                ]
            },
            'DefaultRootObject': 'index.html',
            'Origins': {
                'Quantity': 1,
                'Items': [
                    {
                        'Id': var.website_fqdn,
                        'DomainName': var.website_fqdn+'.s3.amazonaws.com',
                        'CustomOriginConfig': {
                            'HTTPPort': 80,
                            'HTTPSPort': 443,
                            'OriginProtocolPolicy': 'http-only'
                        }
                    },
                ]
            },
            'DefaultCacheBehavior': {
                'TargetOriginId': var.website_fqdn,
                'ForwardedValues': {
                    'QueryString': False,
                    'Cookies': {
                        'Forward': 'none',
                        }
                    },
                'TrustedSigners': {
                    'Enabled': False,
                    'Quantity': 0
                },
                'ViewerProtocolPolicy': 'redirect-to-https',
                'MinTTL': 0,
                'DefaultTTL': 86400,
                'MaxTTL': 31536000
            },
            'Comment': 'Static website cdn',
            'Enabled': True,
            'ViewerCertificate': {
                'CloudFrontDefaultCertificate': False,
                'ACMCertificateArn': cert['CertificateArn'],
                'SSLSupportMethod': 'sni-only',
                'MinimumProtocolVersion': 'TLSv1.1_2016'
            },
            'HttpVersion': 'http2'
        },
        'Tags': {
            'Items': [
                {
                    'Key': 'Name',
                    'Value': var.proj_name
                },
            ]
        }
    }  
)
cdn_dist_id = create_cdn['Distribution']['Id']
cdn_dns_domain = create_cdn['Distribution']['DomainName']
cdn_dist_arn = create_cdn['Distribution']['ARN']
print()
####################################################
##  Set permissions for lambda function to purge cdn
###################################################
print('Creating role for lambda to flush cdn cache...')
invalidate_cdn_policy = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": "cloudfront:CreateInvalidation",
            "Resource": '*'
        },
        {
            "Effect": "Allow",
            "Action": [
                "logs:CreateLogGroup",
                "logs:CreateLogStream",
                "logs:PutLogEvents"
            ],
            "Resource": '*'
        }
    ]
}
invalidate_cdn_policy = json.dumps(invalidate_cdn_policy)
iam = boto3.client('iam')
create_invalidate_cdn_policy = iam.create_policy(
    PolicyName= var.proj_name+'-lambda-invalidate-cdn-policy',
    Path= '/'+var.proj_name+'/lambda/clearcache/',
    PolicyDocument= invalidate_cdn_policy,
    Description= 'Policy attached to lambda. Part of '+var.proj_desc   
)
assume_role_policy = {
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
assume_role_policy = json.dumps(assume_role_policy)
create_invalidate_cdn_role = iam.create_role(
    RoleName= var.proj_name+'-lambda-invalidate-cdn-role',
    Path= '/'+var.proj_name+'/lambda/invalidatecdn/',
    AssumeRolePolicyDocument= assume_role_policy,
    Description= 'Lambda role to purge cdn cache as part of '+var.proj_desc
)
iam.attach_role_policy(
    RoleName= create_invalidate_cdn_role['Role']['RoleName'],
    PolicyArn= create_invalidate_cdn_policy['Policy']['Arn']
)
time.sleep(30)
print()
#################################################
## Create lambda to clear cdn cache
#################################################
print('Creating lambda function to flush cdn cache...')
## zip code for upload
zf = zipfile.ZipFile('invalidate_cdn.zip', 'w')
for name in glob.glob('lambdas/invalidate_cdn/*.py'):
    zf.write(name, os.path.basename(name), zipfile.ZIP_DEFLATED)
zf.close()
## Create lambda
with open('invalidate_cdn.zip', 'rb') as zip_blob:
    create_invalidate_cdn_function = serverless.create_function(
        FunctionName= var.proj_name+'-cdn-cached-objects-invalidation',
        Runtime= 'python3.6',
        Role= create_invalidate_cdn_role['Role']['Arn'],
        Handler= 'invalidate_cdn.lambda_handler',
        Code={
            'ZipFile': zip_blob.read()
        },
        Description= 'Flush cached cdn objects function. Part of '+var.proj_desc,
        Timeout= 180,
        Publish= True,
        Tags={
            'Name': var.proj_name
        },
        Environment={
            'Variables': {
                'CDN_DIST_ID' : cdn_dist_id
            }
        }
)
lambda_policy = serverless.add_permission(
    FunctionName= var.proj_name+'-cdn-cached-objects-invalidation',
    StatementId= 'enable-s3-to-invoke-function',
    Action= 'lambda:InvokeFunction',
    Principal= 's3.amazonaws.com',
    SourceArn= bucket_arn
)
print()
#################################################
## Configure S3 object notifications
#################################################
print('Enabling s3 object notifications...')
s3.put_bucket_notification_configuration(
    Bucket= var.website_fqdn,
    NotificationConfiguration={
        'LambdaFunctionConfigurations': [
            {
                'LambdaFunctionArn': create_invalidate_cdn_function['FunctionArn'],
                'Events': [
                    's3:ObjectCreated:*','s3:ObjectRemoved:*',
                ]
            },
        ]   
    }
)
print()
################################################
#  Set permissions for lambda trigger
###############################################
print('Creating role for lambda to delete logs...')
log_clean_policy = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "logs:CreateLogGroup",
                "logs:CreateLogStream",
                "logs:PutLogEvents"
            ],
            "Resource": '*'
        },
        {
            "Effect": "Allow",
            "Action": [
                "logs:DeleteLogGroup",
                "logs:DescribeLogStreams",
                "logs:DeleteLogStream"
            ],
            "Resource": [
                'arn:aws:logs:*:*:*/aws/lambda/'+create_trigger_function['FunctionName']+'*',
                'arn:aws:logs:*:*:*/aws/lambda/'+create_invalidate_cdn_function['FunctionName']+'*',
                'arn:aws:logs:*:*:*/aws/codebuild/'+var.proj_name+'*'
            ]
        }  
    ]
}
log_clean_policy = json.dumps(log_clean_policy)
iam = boto3.client('iam')
create_log_clean_policy = iam.create_policy(
    PolicyName= var.proj_name+'-lambda-log-clean-policy',
    Path= '/'+var.proj_name+'/lambda/logclean/',
    PolicyDocument= log_clean_policy,
    Description= 'Policy attached to lambda. Part of '+var.proj_desc
)
assume_role_policy = {
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
assume_role_policy = json.dumps(assume_role_policy)
create_log_clean_role = iam.create_role(
    RoleName= var.proj_name+'-lambda-log-clean-role',
    Path= '/'+var.proj_name+'/lambda/logclean/',
    AssumeRolePolicyDocument= assume_role_policy,
    Description= 'Lambda role to cleardown logs. Part of '+var.proj_desc
)
iam.attach_role_policy(
    RoleName= create_log_clean_role['Role']['RoleName'],
    PolicyArn= create_log_clean_policy['Policy']['Arn']
)
time.sleep(30)
print()
################################################
# Create lambda trigger to clean up logs
################################################
print('Creating lambda function to delete logs...')
# zip lambda code for upload
zf = zipfile.ZipFile('log_cleanup.zip', 'w')
for name in glob.glob('lambdas/log_cleanup/*.py'):
    zf.write(name, os.path.basename(name), zipfile.ZIP_DEFLATED)
zf.close()
# Create lambda
serverless = boto3.client('lambda')
with open('log_cleanup.zip', 'rb') as zip_blob:
    create_log_clean_function = serverless.create_function(
        FunctionName= var.proj_name+'-log-cleanup',
        Runtime= 'python3.6',
        Role= create_log_clean_role['Role']['Arn'],
        Handler= 'log_cleanup.lambda_handler',
        Code={
            'ZipFile': zip_blob.read()
        },
        Environment={
            'Variables': {
                'BUILD_LOG': '/aws/codebuild/'+var.proj_name,
                'TRIGGER_LOG': '/aws/lambda/'+create_trigger_function['FunctionName'],
                'CDN_INVALIDATION_LOG': '/aws/lambda/'+create_invalidate_cdn_function['FunctionName']
            }
        },
        Timeout= 120,
        Description= 'Log cleanup function. Part of '+var.proj_desc,
        Tags={
            'Name': var.proj_name
        },
        Publish= True
)
print()
###################################################
## Create cloudwatch event to schedule log cleanup
###################################################
print('Creating schedule to delete logs every 30 days...')
boto3.client('events').put_rule(
    Name= var.proj_name+'-log-cleanup',
    ScheduleExpression= 'rate(30 days)',
    State= 'ENABLED',
    Description= 'Scheduled event to delete logs. Part of '+var.proj_desc
)
time.sleep(10)
boto3.client('events').put_targets(
    Rule= var.proj_name+'-log-cleanup',
    Targets= [
        {
            'Id': var.proj_name+'-log-cleanup',
            'Arn': create_log_clean_function['FunctionArn']
        }
    ]
)
print()
#################################################
## Wait for CDN to be deployed
#################################################
print('''NOTE: It takes on average 30 to 40 minutes for
cloudfront distribution setup to complete, I suggest 
grabbing a tasty beverage at this point, the script will
automatically proceed once the cdn is ready.''')
waiter = cdn.get_waiter('distribution_deployed')
waiter.wait(
    Id= cdn_dist_id,
    WaiterConfig={
        'Delay': 60,
        'MaxAttempts': 60
    }
)
print()
print('cdn successfully deployed...')
print()
#################################################
## Create dns records
#################################################
print('Updating dns for '+var.website_fqdn+'...')
r53.change_resource_record_sets(
HostedZoneId= zone_id,
    ChangeBatch= {
    'Comment': 'Create dns records for '+var.website_fqdn,
    'Changes': [
        {
            'Action': 'UPSERT',
                    'ResourceRecordSet': {
                            'Name': var.website_fqdn,
                            'Type': 'A',
                            'AliasTarget': {
                                'DNSName': cdn_dns_domain,
                                'EvaluateTargetHealth': False,
                                'HostedZoneId': 'Z2FDTNDATAQYW2',
                            }
                    }
                },
        {
            'Action': 'UPSERT',
                    'ResourceRecordSet': {
                            'Name': var.website_fqdn,
                            'Type': 'AAAA',
                            'AliasTarget': {
                                'DNSName': cdn_dns_domain,
                                'EvaluateTargetHealth': False,
                                'HostedZoneId': 'Z2FDTNDATAQYW2'
                            }
                    }
            }
        ]
    }
)
print()
print('Cleaning up zip files...')
dir_path = Path.cwd()
file_path = dir_path / 'file'
for each_file_path in dir_path.glob('*.zip'):
    print(f'removing {each_file_path}')
    each_file_path.unlink()
print()
print('''Deployment complete. The url of your newly 
created source code repository is:
'''
+ssh_repo_url+'''''')
print()