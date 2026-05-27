"""
Error Mapper - Convert AWS exceptions to user-friendly messages
Maps boto3 ClientError exceptions to structured error responses
"""
from typing import Dict, Any, Optional
from botocore.exceptions import ClientError, NoCredentialsError, PartialCredentialsError


# AWS Error Code to User-Friendly Message Mapping
ERROR_MAP = {
    "AccessDeniedException": {
        "code": "MISSING_PERMISSION",
        "message": "Your AWS credentials don't have permission to access this service",
        "suggestion": "Contact your AWS administrator to grant the required IAM permissions"
    },
    "UnauthorizedOperation": {
        "code": "MISSING_PERMISSION",
        "message": "Your AWS credentials don't have permission to perform this operation",
        "suggestion": "Contact your AWS administrator to grant the required IAM permissions"
    },
    "AccessDenied": {
        "code": "MISSING_PERMISSION",
        "message": "Access denied to AWS resource",
        "suggestion": "Verify your IAM permissions and resource policies"
    },
    "InvalidClientTokenId": {
        "code": "INVALID_CREDENTIALS",
        "message": "AWS credentials are invalid or expired",
        "suggestion": "Check your AWS_ACCESS_KEY_ID and refresh your credentials"
    },
    "SignatureDoesNotMatch": {
        "code": "INVALID_CREDENTIALS",
        "message": "AWS credentials signature mismatch",
        "suggestion": "Check your AWS_SECRET_ACCESS_KEY and ensure credentials are correct"
    },
    "ExpiredToken": {
        "code": "EXPIRED_CREDENTIALS",
        "message": "AWS session token has expired",
        "suggestion": "Refresh your AWS credentials and try again"
    },
    "ThrottlingException": {
        "code": "RATE_LIMITED",
        "message": "Too many requests to AWS API",
        "suggestion": "Please wait a moment and try again"
    },
    "RequestLimitExceeded": {
        "code": "RATE_LIMITED",
        "message": "AWS API rate limit exceeded",
        "suggestion": "Please wait a moment before making more requests"
    },
    "DataUnavailableException": {
        "code": "NO_DATA",
        "message": "No data available for the selected period",
        "suggestion": "AWS Cost Explorer data may not be available yet. Cost data typically lags by 24-48 hours"
    },
    "ValidationException": {
        "code": "INVALID_PARAMETERS",
        "message": "Invalid request parameters",
        "suggestion": "Check your date ranges and filter values"
    },
    "InvalidParameterValueException": {
        "code": "INVALID_PARAMETERS",
        "message": "One or more parameters have invalid values",
        "suggestion": "Verify your date ranges, regions, and service names"
    },
    "ResourceNotFoundException": {
        "code": "RESOURCE_NOT_FOUND",
        "message": "AWS resource not found",
        "suggestion": "Verify the resource exists in your account and region"
    },
    "ServiceException": {
        "code": "AWS_SERVICE_ERROR",
        "message": "AWS service encountered an error",
        "suggestion": "This is a temporary AWS service issue. Please try again in a few moments"
    },
    "InternalServerError": {
        "code": "AWS_SERVICE_ERROR",
        "message": "AWS service internal error",
        "suggestion": "This is a temporary AWS issue. Please try again later"
    },
}


# Service-specific error mappings
SERVICE_SPECIFIC_ERRORS = {
    "ce": {  # Cost Explorer
        "CostExplorerNotEnabledException": {
            "code": "SERVICE_NOT_ENABLED",
            "message": "AWS Cost Explorer is not enabled for this account",
            "suggestion": "Enable Cost Explorer in the AWS Billing console (Settings → Cost Explorer)"
        },
        "BillNotAvailableForAccountException": {
            "code": "NO_DATA",
            "message": "Billing data not available for this account",
            "suggestion": "Ensure billing is activated and Cost Explorer is enabled"
        },
    },
    "organizations": {
        "AWSOrganizationsNotInUseException": {
            "code": "SERVICE_NOT_ENABLED",
            "message": "AWS Organizations is not enabled for this account",
            "suggestion": "This account is not part of an AWS Organization"
        },
        "AccessDeniedForDependencyException": {
            "code": "MISSING_PERMISSION",
            "message": "Missing permissions for required service",
            "suggestion": "Ensure all required service permissions are granted"
        },
    },
    "logs": {
        "ResourceNotFoundException": {
            "code": "RESOURCE_NOT_FOUND",
            "message": "CloudWatch log group not found",
            "suggestion": "Verify the log group name and region"
        },
    }
}


class ErrorMapper:
    """Convert AWS exceptions to user-friendly structured errors"""
    
    @staticmethod
    def map_error(exception: Exception, service: Optional[str] = None) -> Dict[str, Any]:
        """
        Map an exception to a structured error response.
        
        Args:
            exception: The exception to map
            service: AWS service name (e.g., 'ce', 'ec2', 'organizations')
            
        Returns:
            Structured error dict with code, message, and suggestion
        """
        
        # Handle credential errors
        if isinstance(exception, NoCredentialsError):
            return {
                "code": "NO_CREDENTIALS",
                "message": "AWS credentials not found",
                "suggestion": "Configure AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY environment variables"
            }
        
        if isinstance(exception, PartialCredentialsError):
            return {
                "code": "INCOMPLETE_CREDENTIALS",
                "message": "AWS credentials are incomplete",
                "suggestion": "Ensure both AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY are configured"
            }
        
        # Handle boto3 ClientError
        if isinstance(exception, ClientError):
            error_code = exception.response.get('Error', {}).get('Code', 'UnknownError')
            
            # Check service-specific errors first
            if service and service in SERVICE_SPECIFIC_ERRORS:
                if error_code in SERVICE_SPECIFIC_ERRORS[service]:
                    return SERVICE_SPECIFIC_ERRORS[service][error_code]
            
            # Check general error map
            if error_code in ERROR_MAP:
                return ERROR_MAP[error_code]
            
            # Fallback for unmapped errors
            aws_message = exception.response.get('Error', {}).get('Message', str(exception))
            return {
                "code": "AWS_ERROR",
                "message": f"AWS service error: {error_code}",
                "suggestion": "Please check your AWS account configuration and try again",
                "raw_error": aws_message  # Include for debugging, strip in production
            }
        
        # Generic exception fallback
        return {
            "code": "UNKNOWN_ERROR",
            "message": "An unexpected error occurred",
            "suggestion": "Please try again or contact support if the issue persists"
        }
    
    @staticmethod
    def create_error_response(exception: Exception, service: Optional[str] = None, 
                            context: Optional[str] = None) -> Dict[str, Any]:
        """
        Create a full error response suitable for returning to the user.
        
        Args:
            exception: The exception to map
            service: AWS service name
            context: Additional context (e.g., "Failed to fetch cost data")
            
        Returns:
            Complete error response dict
        """
        error_details = ErrorMapper.map_error(exception, service)
        
        response = {
            "success": False,
            "data": None,
            "error": {
                "code": error_details["code"],
                "message": error_details["message"],
                "suggestion": error_details.get("suggestion", "")
            }
        }
        
        if context:
            response["error"]["context"] = context
        
        return response
