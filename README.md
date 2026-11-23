# BBL.BOXTV Server V3

Backend FastAPI para gerenciamento autorizado de launchers Android/TV Box.

## Recursos
- Ativação por chave e ID de dispositivo
- Painel para gerar, ativar e desativar códigos de ativação
- Bloqueio/desbloqueio e vencimento
- Layout por dispositivo
- Upload automático de APK com extração de nome/pacote/versão
- Catálogo e download de APK
- Notificações e logs
- Informações de fabricante/modelo/Android/versão da launcher
- SQLite local ou PostgreSQL no Render

## Rodar local
```bash
pip install -r requirements.txt
set ADMIN_KEY=uma-chave-forte
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```
No Linux/macOS use `export ADMIN_KEY=...`.

Abra `http://localhost:8000` e informe a ADMIN_KEY.

## Variáveis
Veja `.env.example`. Em produção, use uma ADMIN_KEY forte e PostgreSQL persistente.

## Launcher
1. `POST /api/enroll` com chave de ativação e dados do aparelho.
2. Guardar `device_id` e `device_token` retornados.
3. Consultar `GET /api/devices/{device_id}/policy` com `Authorization: Bearer <device_token>`.
4. A resposta contém bloqueio, vencimento, layout e apps autorizados.
5. `GET /api/devices/{device_id}/notifications` retorna notificações pendentes.

A instalação/atualização de APK deve respeitar as permissões e políticas do Android do aparelho.

## Novidades da V3 atualizada
- Nome do serviço Render corrigido para `bbl-tvbox-manager-v3`.
- Nova aba **Ativações** no painel.
- Geração automática de códigos no formato `BBL-XXXX-XXXX`.
- Possibilidade de criar código personalizado e ativar/desativar códigos existentes.


## Checkout Pix da BBL Launcher

- Página do cliente: `/launcher`
- Criar pedido: `POST /api/store/orders` com `customer_name`, `whatsapp` e `device_model`.
- Consultar pagamento: `GET /api/store/orders/{order_id}?token={order_token}`.
- Webhook do Mercado Pago: `/api/store/mercadopago/webhook`.
- O valor é fixo no servidor em R$ 20,00. Após confirmação consultada no Mercado Pago, o sistema cria um código de ativação de uso único.
- Configure `MERCADO_PAGO_ACCESS_TOKEN` como segredo no ambiente do serviço Render. Configure também `MERCADO_PAGO_WEBHOOK_SECRET` se a assinatura estiver ativa no painel do Mercado Pago e `MERCADO_PAGO_PAYER_EMAIL` se quiser substituir o e-mail padrão.
- A URL do webhook é montada a partir do endereço público da requisição que cria o Pix. Cadastre `https://<dominio-do-servico>/api/store/mercadopago/webhook` como URL de notificações de pagamento no Mercado Pago.
- O fluxo de compra permanece indisponível com resposta 503 enquanto o token não estiver configurado. A chave de acesso nunca deve ir para o HTML ou navegador.
