"""Capabilities of the official integration available to this installation."""

from dataclasses import dataclass
from enum import StrEnum


class Capability(StrEnum):
    AUTO_PUBLISH = "AUTO_PUBLISH"
    ASSISTED_PUBLISH = "ASSISTED_PUBLISH"
    UNAVAILABLE = "UNAVAILABLE"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"


PLATFORM_NAMES = {
    "youtube": "YouTube Shorts",
    "instagram": "Instagram Reels",
    "facebook": "Facebook Reels",
    "tiktok": "TikTok",
    "kwai": "Kwai",
}


@dataclass(frozen=True)
class Connector:
    platform: str
    capability: Capability
    official_url: str
    instructions: str

    def publish(self, *_args, **_kwargs):
        raise NotImplementedError(
            "Este conector usa publicação assistida: exporte, publique no aplicativo "
            "oficial e confirme a conclusão."
        )


def registry(youtube_authenticated: bool = False) -> dict[str, Connector]:
    """No restricted integration is advertised as automatically available."""
    return {
        "youtube": Connector(
            "youtube",
            Capability.AUTO_PUBLISH if youtube_authenticated else Capability.AUTH_REQUIRED,
            "https://studio.youtube.com/",
            "Conecte um canal usando OAuth oficial. A classificação como Short depende "
            "do YouTube. O envio privado não é uma publicação pública.",
        ),
        "instagram": Connector(
            "instagram", Capability.ASSISTED_PUBLISH, "https://www.instagram.com/",
            "Conta pessoal: publique o vídeo e a legenda no Instagram oficial. "
            "Se o navegador não oferecer Reels, transfira o pacote ao celular. "
            "A API de publicação requer conta profissional elegível e permissões.",
        ),
        "facebook": Connector(
            "facebook", Capability.ASSISTED_PUBLISH, "https://www.facebook.com/",
            "Perfil pessoal: publique pelo Facebook oficial. A integração para Páginas "
            "é distinta e requer acesso e permissões próprios.",
        ),
        "tiktok": Connector(
            "tiktok", Capability.ASSISTED_PUBLISH, "https://www.tiktok.com/upload",
            "Envie no TikTok oficial e confira as opções de audiência e direitos. "
            "Publicação direta exige aprovação da Content Posting API; uso restrito "
            "às próprias contas não presume elegibilidade.",
        ),
        "kwai": Connector(
            "kwai", Capability.ASSISTED_PUBLISH, "https://www.kwai.com/",
            "Transfira o vídeo e a legenda ao aplicativo oficial Kwai e conclua nele. "
            "Não há integração automática comprovada para esta conta brasileira.",
        ),
    }
