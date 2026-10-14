"""Save, remove and test the signed-in user's provider credentials. Responses never contain a key."""

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.deps import get_credential_service, get_current_user
from app.core.secret_box import SecretsNotConfigured
from app.models import User
from app.schemas.provider_settings import ProviderName, ProviderSaveRequest, ProviderStatus, ProviderTestResult
from app.services.credential_service import CredentialService

router = APIRouter(prefix="/settings/providers")

_NO_STORE = {"Cache-Control": "no-store"}


@router.get("", response_model=list[ProviderStatus])
async def list_providers(
    response: Response,
    current_user: User = Depends(get_current_user),
    service: CredentialService = Depends(get_credential_service),
) -> list[ProviderStatus]:
    response.headers.update(_NO_STORE)
    return await service.status(current_user.id)


@router.put("/{provider}", response_model=ProviderStatus)
async def save_provider(
    provider: ProviderName,
    payload: ProviderSaveRequest,
    response: Response,
    current_user: User = Depends(get_current_user),
    service: CredentialService = Depends(get_credential_service),
) -> ProviderStatus:
    response.headers.update(_NO_STORE)
    try:
        return await service.save(
            current_user,
            provider,
            api_key=payload.api_key.get_secret_value() if payload.api_key is not None else None,
            base_url=payload.base_url,
            base_url_provided="base_url" in payload.model_fields_set,
        )
    except SecretsNotConfigured as exc:
        # The message names the setting and how to generate a key; it never contains a value.
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from None
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from None
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None


@router.delete("/{provider}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_provider(
    provider: ProviderName,
    current_user: User = Depends(get_current_user),
    service: CredentialService = Depends(get_credential_service),
) -> Response:
    await service.delete(current_user.id, provider)
    return Response(status_code=status.HTTP_204_NO_CONTENT, headers=_NO_STORE)


@router.post("/{provider}/test", response_model=ProviderTestResult)
async def test_provider(
    provider: ProviderName,
    response: Response,
    current_user: User = Depends(get_current_user),
    service: CredentialService = Depends(get_credential_service),
) -> ProviderTestResult:
    response.headers.update(_NO_STORE)
    return ProviderTestResult(**await service.test(current_user.id, provider))
