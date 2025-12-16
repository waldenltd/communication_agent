"""
PDF Fetcher Utility

Fetches PDF files from service APIs for email attachments.
"""

from typing import Optional, Dict, Any
import requests
from src import logger


def fetch_sales_receipt_pdf(
    receipt_id: str,
    api_base_url: str,
    timeout: int = 30
) -> Optional[bytes]:
    """
    Fetch a sales receipt PDF from the service API.

    Args:
        receipt_id: The receipt ID to fetch PDF for
        api_base_url: Base URL of the service API
        timeout: Request timeout in seconds

    Returns:
        PDF content as bytes, or None if fetch fails
    """
    try:
        base_url = api_base_url.rstrip('/')
        pdf_url = f"{base_url}/api/Invoice/{receipt_id}/pdf"

        logger.info(
            'Fetching sales receipt PDF',
            receipt_id=receipt_id,
            url=pdf_url
        )

        response = requests.get(pdf_url, timeout=timeout)

        if response.status_code == 200:
            content_type = response.headers.get('Content-Type', '')
            if 'pdf' not in content_type.lower() and len(response.content) > 0:
                logger.warn(
                    'PDF endpoint returned unexpected content type',
                    content_type=content_type,
                    receipt_id=receipt_id
                )

            logger.info(
                'Successfully fetched sales receipt PDF',
                receipt_id=receipt_id,
                size_bytes=len(response.content)
            )

            return response.content

        elif response.status_code == 404:
            logger.warn(
                'Sales receipt PDF not found',
                receipt_id=receipt_id,
                status_code=response.status_code
            )
            return None

        else:
            logger.error(
                'Failed to fetch sales receipt PDF',
                receipt_id=receipt_id,
                status_code=response.status_code,
                response_text=response.text[:200] if response.text else None
            )
            return None

    except requests.Timeout:
        logger.error(
            'Timeout fetching sales receipt PDF',
            receipt_id=receipt_id,
            timeout=timeout
        )
        return None

    except requests.RequestException as e:
        logger.error(
            'Request error fetching sales receipt PDF',
            err=e,
            receipt_id=receipt_id
        )
        return None

    except Exception as e:
        logger.error(
            'Unexpected error fetching sales receipt PDF',
            err=e,
            receipt_id=receipt_id
        )
        return None


def fetch_work_order_pdf(
    work_order_id: str,
    api_base_url: str,
    timeout: int = 30
) -> Optional[bytes]:
    """
    Fetch a work order PDF from the service API.

    Args:
        work_order_id: The work order ID to fetch PDF for
        api_base_url: Base URL of the service API
        timeout: Request timeout in seconds

    Returns:
        PDF content as bytes, or None if fetch fails

    Example:
        >>> pdf_content = fetch_work_order_pdf('12345', 'https://api.example.com')
        >>> if pdf_content:
        ...     # Use pdf_content for email attachment
    """
    try:
        # Remove trailing slash from base URL if present
        base_url = api_base_url.rstrip('/')

        # Construct the PDF endpoint URL
        pdf_url = f"{base_url}/api/workorder/{work_order_id}/pdf"

        logger.info(
            f'Fetching work order PDF',
            work_order_id=work_order_id,
            url=pdf_url
        )

        # Make the request
        response = requests.get(pdf_url, timeout=timeout)

        # Check for successful response
        if response.status_code == 200:
            # Verify we got PDF content
            content_type = response.headers.get('Content-Type', '')
            if 'pdf' not in content_type.lower() and len(response.content) > 0:
                logger.warn(
                    f'PDF endpoint returned unexpected content type',
                    content_type=content_type,
                    work_order_id=work_order_id
                )

            logger.info(
                f'Successfully fetched work order PDF',
                work_order_id=work_order_id,
                size_bytes=len(response.content)
            )

            return response.content

        elif response.status_code == 404:
            logger.warn(
                f'Work order PDF not found',
                work_order_id=work_order_id,
                status_code=response.status_code
            )
            return None

        else:
            logger.error(
                f'Failed to fetch work order PDF',
                work_order_id=work_order_id,
                status_code=response.status_code,
                response_text=response.text[:200] if response.text else None
            )
            return None

    except requests.Timeout:
        logger.error(
            f'Timeout fetching work order PDF',
            work_order_id=work_order_id,
            timeout=timeout
        )
        return None

    except requests.RequestException as e:
        logger.error(
            f'Request error fetching work order PDF',
            err=e,
            work_order_id=work_order_id
        )
        return None

    except Exception as e:
        logger.error(
            f'Unexpected error fetching work order PDF',
            err=e,
            work_order_id=work_order_id
        )
        return None
