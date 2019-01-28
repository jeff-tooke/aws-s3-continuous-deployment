import boto3
import os
import time
import datetime

def lambda_handler(event, context):
    time.sleep(60)
    dt = datetime.datetime.now()
    call_ref = dt.strftime('%d/%m/%Y %H:%M:%S')
    boto3.client('cloudfront').create_invalidation(
    DistributionId=  os.environ['CDN_DIST_ID'],
    InvalidationBatch={
            'Paths': {
                'Quantity': 1,
                'Items': [
                    '/*',
                ]
            },
            'CallerReference': call_ref
        }
)