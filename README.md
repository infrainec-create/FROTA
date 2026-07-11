# FrotaControl

Aplicação Streamlit para controle de frota, com os registros armazenados em uma planilha privada do Google Sheets no Google Drive e um analista de IA para apoiar o planejamento de manutenção.

## Executar localmente

```bash
python3 -m pip install -r requirements.txt
mkdir -p .streamlit
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
streamlit run streamlit_app.py
```

Preencha `.streamlit/secrets.toml` antes de iniciar. Esse arquivo é ignorado pelo Git.

Se o banco SQLite atual já tiver dados, depois de configurar os secrets execute uma única vez:

```bash
python3 migrate_sqlite_to_sheets.py frota.db
```

Confirme os registros na planilha antes de descartar o arquivo SQLite. Não execute o migrador duas vezes na mesma planilha, pois ele inclui novas linhas.

## Configuração do banco no Google Drive

1. Crie uma planilha Google Sheets vazia no Drive e copie o ID da URL para `google_sheet_id`.
2. No Google Cloud, habilite as APIs **Google Sheets API** e **Google Drive API**.
3. Crie uma conta de serviço, gere a chave JSON e copie seus campos para `[gcp_service_account]` nos secrets.
4. Compartilhe a planilha com o e-mail `client_email` da conta de serviço, com permissão de **Editor**.
5. Na primeira inicialização, o app cria as abas de dados automaticamente.

## Analista de IA

Adicione `OPENAI_API_KEY` aos secrets para ativar o parecer de manutenção. O analista usa o histórico de abastecimentos e manutenções apenas do veículo selecionado. Ele é apoio à decisão e não substitui a inspeção de um profissional qualificado.

## Publicar no GitHub e Streamlit Cloud

```bash
git init
git add .
git commit -m "Publica FrotaControl no Streamlit"
git branch -M main
git remote add origin https://github.com/SEU_USUARIO/SEU_REPOSITORIO.git
git push -u origin main
```

Depois, no [Streamlit Community Cloud](https://share.streamlit.io/), crie um app apontando para o repositório, branch `main` e arquivo `streamlit_app.py`. Em **Advanced settings → Secrets**, cole o conteúdo do seu `secrets.toml` — nunca envie essas credenciais ao GitHub.
