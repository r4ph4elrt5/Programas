"""Desktop launcher, offline diagnosis and explicitly enabled loopback API."""

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

from . import __version__


def main():
    parser = argparse.ArgumentParser(description="MultiPost Desktop")
    parser.add_argument("--data-dir", type=Path, help="Diretório persistente de dados")
    parser.add_argument("--diagnostics", action="store_true", help="Diagnóstico offline, sem credenciais")
    parser.add_argument("--smoke-test", action="store_true", help="Teste de navegação em banco temporário")
    parser.add_argument("--api", action="store_true", help="API local autenticada em 127.0.0.1:8765")
    args = parser.parse_args()
    if args.diagnostics:
        from .service import AppService
        service = AppService(args.data_dir)
        try:
            print(json.dumps({"version": __version__, "python": sys.version.split()[0],
                              "ffmpeg": shutil.which("ffmpeg"), "ffprobe": shutil.which("ffprobe"),
                              "data_dir": str(service.data_dir), "database": "ok", "stats": service.stats(),
                              "remote_validation": "not_performed"}, ensure_ascii=False, indent=2))
        finally:
            service.close()
        return
    if args.api:
        try:
            import uvicorn
            from .api import create_api
        except ImportError:
            parser.error("Instale o módulo opcional: pip install -e '.[api]'")
        from .service import AppService
        service = AppService(args.data_dir)
        print(f"API local: credencial no arquivo {service.data_dir / 'api-key'}. Não compartilhe o conteúdo.")
        try:
            uvicorn.run(create_api(service), host="127.0.0.1", port=8765, access_log=False)
        finally:
            service.close()
        return
    from .ui import launch
    if args.smoke_test:
        with tempfile.TemporaryDirectory(prefix="multipost-smoke-") as directory:
            launch(Path(directory), smoke_test=True)
    else:
        launch(args.data_dir)


if __name__ == "__main__":
    main()
