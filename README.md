# QuintoAndar × Prudential — Embedded Insurance (protótipo)

App mobile (Flask + PostgreSQL) que simula o fluxo do QuintoAndar com seguro
**embedded** da Prudential contratado junto ao aluguel. Cada proposta enviada
grava no banco de dados — incluindo o plano de seguro escolhido — e o painel
`/admin` calcula o **take-rate** do seguro, a métrica central da proposta comercial.

## O que tem
- `/` — app com 3 telas (home, imóvel, proposta) numa moldura de iPhone
- `/api/imoveis`, `/api/planos`, `/api/propostas` — API que lê/grava no banco
- `/admin` — painel com propostas, take-rate e receita mensal de seguro

## Rodar localmente
```bash
pip install -r requirements.txt
python app.py            # usa SQLite (local.db) automaticamente
# abre http://localhost:5000
```

## Publicar no Render (com PostgreSQL)

### Opção A — Blueprint (automático, recomendado)
1. Suba esta pasta para um repositório no GitHub.
2. No Render: **New +** → **Blueprint** → conecte o repositório.
3. O arquivo `render.yaml` cria sozinho o banco Postgres e o web service,
   já ligando a variável `DATABASE_URL`. Clique em **Apply**.
4. Aguarde o build. Pronto — o app sobe e cria/popula as tabelas na primeira
   execução.

### Opção B — Manual
1. No Render: **New +** → **PostgreSQL** → crie o banco (plano Free). Copie a
   *Internal Database URL*.
2. **New +** → **Web Service** → conecte o repositório.
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `gunicorn app:app`
3. Em **Environment**, adicione:
   - `DATABASE_URL` = a URL do banco do passo 1
4. Deploy. As tabelas são criadas e populadas automaticamente no primeiro boot.

## Observações
- O código aceita tanto `postgres://` quanto `postgresql://` (o Render usa o
  primeiro; o app converte).
- O seed roda uma vez (só insere se as tabelas estiverem vazias), então é seguro
  reiniciar.
- As imagens dos imóveis são SVG embutidos (`static/images.js`) — funcionam
  offline, sem depender de serviços externos.

## Estrutura
```
app.py                # servidor Flask + modelos + API + seed
render.yaml           # blueprint do Render (web + banco)
requirements.txt
Procfile
templates/index.html  # o app (3 telas)
templates/admin.html  # painel de propostas / take-rate
static/images.js      # imagens SVG dos apartamentos
```
