# Instalação remota de aplicativos - V3

O launcher V3 lê `download_url`, `version_code` e `sha256` enviados pelo servidor V3.

Fluxo:
1. O administrador faz upload do APK no painel e adiciona o app ao layout/dispositivo.
2. A TV Box sincroniza a política a cada 60 segundos.
3. Se o app estiver ausente ou desatualizado, o launcher baixa o APK e abre o instalador do Android.
4. Na primeira vez, o Android pode pedir para habilitar **Permitir desta fonte** para BBL.BOXTV.
5. Em Android comum, a confirmação final de instalação pode ser exigida pelo sistema. Instalação silenciosa requer Device Owner/MDM, app de sistema ou ambiente gerenciado compatível.

O APK é verificado por SHA-256 quando o servidor fornece o hash.
