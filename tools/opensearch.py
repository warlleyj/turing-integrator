import json
import os
import re
from datetime import datetime, timezone
from html import parser, unescape
from socket import timeout

import requests

DATA_IN_USE = {
    'host': os.environ.get('KNOWLEDGE_HUB_HOST') or os.environ.get('KNOWLEDGE_HUB_API_HOST', 'https://ca-indexadormaple-prd.ambitiousbush-dac46abd.centralus.azurecontainerapps.io'),
    'api_key': os.environ.get('KNOWLEDGE_HUB_API_KEY'),
    'upsert_path': '/documents/upsert',
    'search_path': os.environ.get('KNOWLEDGE_HUB_SEARCH_PATH', '/search'),
    'delete_path': os.environ.get('KNOWLEDGE_HUB_DELETE_PATH', '/documents'),
    'timeout': int(os.environ.get('KNOWLEDGE_HUB_API_TIMEOUT', '30')),
    'namespace': os.environ.get('KNOWLEDGE_HUB_NAMESPACE', 'portal-warlley'),
}


def get_upsert_url(host: str | None = None) -> str:
    configured_host = (host or DATA_IN_USE['host']).strip()
    if not configured_host:
        raise ValueError('KNOWLEDGE_HUB_HOST ainda não foi configurado.')

    return configured_host.rstrip('/') + DATA_IN_USE['upsert_path']


def get_search_url(host: str | None = None) -> str:
    configured_host = (host or DATA_IN_USE['host']).strip()
    if not configured_host:
        raise ValueError('KNOWLEDGE_HUB_HOST ainda nao foi configurado.')

    return configured_host.rstrip('/') + DATA_IN_USE['search_path']

def get_delete_url(host: str | None = None) -> str:
    configured_host = (host or DATA_IN_USE['host']).strip()
    if not configured_host:
        raise ValueError('KNOWLEDGE_HUB_HOST ainda nao foi configurado.')

    return configured_host.rstrip('/') + DATA_IN_USE['delete_path']


def get_headers(api_key: str | None = None) -> dict:
    configured_api_key = (api_key or DATA_IN_USE['api_key']).strip()
    if not configured_api_key:
        raise ValueError('KNOWLEDGE_HUB_API_KEY ainda não foi configurado.')

    return {
        'X-API-Key': configured_api_key,
        'Content-Type': 'application/json',
    }


def build_document(external_id, title: str, text: str, payload: dict | None = None) -> dict:
    return {
        'external_id': str(external_id),
        'title': title,
        'text': text,
        'payload': payload or {},
    }


def build_document_from_sp_post(sp_post: dict, mbtype: str = 'manual') -> dict:
    date_update = _get_modification_date(sp_post)
    payload = {
        'id': sp_post['id'],
        'mbtype': mbtype,
        'url': sp_post.get('pathFragment') or sp_post.get('url'),
        'area': sp_post.get('tagFragmentArea') or sp_post.get('area', []),
        'theme': sp_post.get('tagFragmentTheme') or sp_post.get('theme', []),
        'functiontags': sp_post.get('functiontags', []),
        'publication_date': sp_post.get('publicationDate') or sp_post.get('publication_date') or date_update,
        'modification_date': sp_post.get('modification_date') or date_update,
        'image': sp_post.get('image', ''),
        'highlights': sp_post.get('highlights', False),
        'buttonText': sp_post.get('buttonTextFragment') or sp_post.get('buttonText'),
        'description': _normalize_text(sp_post.get('descriptionFragment') or sp_post.get('description', '')),
        'eventType': sp_post.get('eventType', []),
        'initialDate': sp_post.get('initialDate', ''),
        'finishDate': sp_post.get('finishDate', ''),
        'allDay': sp_post.get('allDay', ''),
        'buttonLink': sp_post.get('buttonLink', ''),
    }
    payload = {key: value for key, value in payload.items() if value not in (None, '', [], {})}

    raw_text = sp_post.get('m') or sp_post.get('text', '')
    text = _normalize_text(raw_text)

    return build_document(
        external_id=sp_post['id'],
        title=sp_post.get('t') or sp_post.get('title', ''),
        text=text,
        payload=payload,
    )


def upsert_documents(
    documents: list[dict],
    host: str | None = None,
    api_key: str | None = None,
    timeout: int | None = None,
):
    url = get_upsert_url(host)
    request_body = {'documents': documents}
    response = requests.post(
        url,
        json=request_body,
        headers=get_headers(api_key),
        timeout=timeout or DATA_IN_USE['timeout'],
    )

    try:
        response.raise_for_status()
    except requests.HTTPError:
        print('Erro ao enviar documentos para OpenSearch')
        print('URL:', url)
        print('Status:', response.status_code)
        print('Resposta:', response.text)
        print('Payload enviado:', json.dumps(request_body, ensure_ascii=False, default=str))
        raise

    try:
        response_body = response.json()
    except ValueError:
        response_body = response.text

    print('Documentos enviados com sucesso:', response.status_code, response_body, json.dumps(request_body))
    return response


def get_all_opensearch(offset: int, limit: int, mbtype: str = 'all', host: str | None = None, api_key: str | None = None, timeout: int | None = None):
    payload = {
        'query': '',
        'offset': offset,
        'limit': limit,
    }

    if mbtype != 'all':
        payload['filters'] = {'mbtype': mbtype}
        payload['filter_type'] = 'and'

    headers = get_headers(api_key)
    base_timeout = timeout or DATA_IN_USE['timeout']
    url = get_search_url(host)

    response = requests.post(url, json=payload, headers=headers, timeout=base_timeout)
    response.raise_for_status()
    return response.json()


def getAllOpenSearchIds(mbtype: str = 'all'):
    ids = []
    limit = 200

    for page in range(0, 100):
        offset = page * limit
        try:
            datas = get_all_opensearch(offset, limit, mbtype)
        except requests.RequestException as error:
            print('Erro ao buscar dados do OpenSearch:', error)
            break

        documents = _extract_documents(datas)
        if not documents:
            break

        for document in documents:
            payload = document.get('payload', {}) if isinstance(document, dict) else {}
            item_mbtype = payload.get('mbtype', document.get('mbtype') if isinstance(document, dict) else None)

            if mbtype != 'all' and item_mbtype != mbtype:
                print("Ignorando documento com mbtype diferente:", item_mbtype)
                continue

            document_id = (
                payload.get('id')
                or document.get('external_id')
                or document.get('id')
            )
            if document_id is None:
                continue

            publication_date = (
                payload.get('publication_date')
                or document.get('publication_date')
                or document.get('created_at')
                or datetime.now(timezone.utc).isoformat()
            )
            modification_date = (
                payload.get('modification_date')
                or document.get('modification_date')
                or document.get('updated_at')
                or publication_date
            )

            ids.append(
                {
                    'id': str(document_id),
                    'publication_date': publication_date,
                    'modification_date': modification_date,
                }
            )

        if len(documents) < limit:
            break

    return ids


def send(
    sp_post: dict,
    mbtype: str = 'manual',
    host: str | None = None,
    api_key: str | None = None,
    timeout: int | None = None,
) -> dict:
    document = build_document_from_sp_post(sp_post, mbtype)
    upsert_documents([document], host=host, api_key=api_key, timeout=timeout)
    return document


def _get_modification_date(sp_post: dict) -> str:
    last_activity_at = sp_post.get('lastActivityAt')
    if isinstance(last_activity_at, (int, float)):
        return datetime.fromtimestamp(last_activity_at / 1000, tz=timezone.utc).isoformat()

    return sp_post.get('modification_date', datetime.now(timezone.utc).isoformat())


def _normalize_text(content) -> str:
    if not isinstance(content, str):
        return str(content or '')

    if '<' not in content or '>' not in content:
        return ' '.join(content.split()).strip()

    text = re.sub(
        r'<img[^>]+src=["\']([^"\']+)["\'][^>]*>',
        lambda match: f' [{unescape(match.group(1))}] ',
        content,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>.*?</a>',
        lambda match: f' [{unescape(match.group(1))}] ',
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    text = re.sub(r'<[^>]+>', ' ', text)
    text = unescape(text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def _extract_documents(data) -> list[dict]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]

    if not isinstance(data, dict):
        return []

    for key in ('documents', 'items', 'hits', 'results', 'data'):
        value = data.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            for nested_key in ('documents', 'items', 'hits', 'results', 'data'):
                nested_value = value.get(nested_key)
                if isinstance(nested_value, list):
                    return nested_value

    return []

def delete(id, remove_images = False):
    headers = {
        'X-API-Key': DATA_IN_USE['api_key'],
        'Content-Type': 'application/json'
    }

    data = {
        'external_ids' : [id],
    }

    url = get_delete_url(DATA_IN_USE['host'])

    response = requests.delete(url, json=data, headers=headers, verify=False)
    print('Publicação deletada com sucesso:', response.status_code, json.dumps(data))

def get_only_texts(html: str) -> str:
    text_captured = ''
    matches = re.findall(r'<(?:span|p)[^>]*>(.*?)</(?:span|p)>', html, flags=re.IGNORECASE | re.DOTALL)

    if matches:
        text_captured = ' '.join(matches)

    text_captured = re.sub(r'<[^>]*>', '', text_captured)  # Remove tags restantes
    # Permite letras, números, espaço, underline, traço e pontuações .,;:!?
    text_captured = re.sub(r'[^\w\s\-\.,;:!\?]', '', text_captured)

    return text_captured.strip()

def get_text_with_images_and_pdf(html: str) -> str:
    links_substituidos = {}
    contador = 0

    def substituir_img(match):
        nonlocal contador
        src = unescape(match.group(1))
        marcador = f"__ARQ{contador}__"
        links_substituidos[marcador] = "[" + src + "]"   
        contador += 1
        return marcador

    def substituir_pdf(match):
        nonlocal contador
        href = unescape(match.group(1))
        marcador = f"__ARQ{contador}__"
        links_substituidos[marcador] = "[" + href + "]"
        contador += 1
        return marcador

    def substituir_link(match):
        nonlocal contador
        href = unescape(match.group(1))
        if href.lower().endswith('.pdf'):
            return match.group(0)  # Ignora, já tratado no bloco PDF
        marcador = f"__ARQ{contador}__"
        links_substituidos[marcador] = f"[{href}]"
        contador += 1
        return marcador

    # Substitui imagens
    html = re.sub(
        r'<img[^>]+src=["\']([^"\']+)["\'][^>]*>',
        substituir_img,
        html,
        flags=re.IGNORECASE
    )

    # Substitui PDFs
    html = re.sub(
        r'<a[^>]+href=["\']([^"\']+\.pdf(\?[^"\']*)?)["\'][^>]*>.*?</a>',
        substituir_pdf,
        html,
        flags=re.IGNORECASE | re.DOTALL
    )

    # Substitui links genéricos (não PDF)
    html = re.sub(
        r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>.*?</a>',
        substituir_link,
        html,
        flags=re.IGNORECASE | re.DOTALL
    )

    # Extrai e limpa texto
    matches = re.findall(
        r'<(span|p|div|a)[^>]*>(.*?)</\1>',
        html,
        flags=re.IGNORECASE | re.DOTALL
    )
    textos_capturados = ' '.join([unescape(m[1]) for m in matches])
    texto_limpo = re.sub(r'<[^>]+>', '', textos_capturados)
    texto_limpo = re.sub(r'[^\w\s\[\]_\-.:/?]', '', texto_limpo, flags=re.UNICODE)

    for marcador, link in links_substituidos.items():
        texto_limpo = texto_limpo.replace(marcador, link)

    texto_limpo = texto_limpo.replace('\n', '')
    texto_limpo = ' '.join(texto_limpo.split())
    texto_limpo = re.sub(r'\s+', ' ', texto_limpo).strip()
    return texto_limpo

def get_tags_from_kb(category, tag_type) -> list:
    if tag_type == 'area':
        tag_relation = {
            'academico': "maple-bear:area/academico",
            "administrativo": "maple-bear:area/administrativo-financeiro",
            "marketing": "maple-bear:area/marketing",
            "comercial": "maple-bear:area/comercial-vendas",
            "gente": "maple-bear:area/gente",
            "gestao-escolar": "maple-bear:area/gestaoescolar",
            "tecnologia": "maple-bear:area/tecnologia"
        }
    elif tag_type == 'theme':
        tag_relation = {
            '67583dbae71a454adb45b281': "maple-bear:theme/estudos-de-mercado",
            '67583ff2e71a454adb4a511a': "maple-bear:theme/edtech-sistemas",
            '67584002e71a454adb4a7626': "maple-bear:theme/treinamentos",
            '6758401ce71a454adb4aad04': "maple-bear:theme/enxoval-de-peças",
            '67584556e71a454adb55c843': "maple-bear:theme/acoes-parcerias",
            '67584560e71a454adb55e0bf': "maple-bear:theme/suporte",
            '67584577e71a454adb560f2a': "maple-bear:theme/treinamentos-&-eventos",
            '6758458de71a454adb563f81': "maple-bear:theme/arquitetura-expansao",
            '6758459fe71a454adb5665a6': "maple-bear:theme/projetos-escolares",
            '675845aee71a454adb5684d1': "maple-bear:theme/programas-maple-bear",
            '675845c7e71a454adb56bc39': "maple-bear:theme/ecossistema-maple-bear",
            '675845d5e71a454adb56da17': "maple-bear:theme/comunica--o",
            '675845eae71a454adb570a17': "maple-bear:theme/matricula-rematricula",
            '675845f9e71a454adb5727ca': "maple-bear:theme/gestao-escolar"
        }
    elif tag_type == 'function':
        tag_relation = {
            "owner": "maple-bear:function/owner"
        }
    else:
        return []

    tag = tag_relation.get(category)
    return [tag] if tag else []

def integrationStatus(opensearchDatas, spPost):
    for opensearchData in opensearchDatas:
        if int(opensearchData['id']) == int(spPost['id']):
            dateOpensearch = parser.isoparse(opensearchData['modification_date']).replace(microsecond=0)
            dateSpPost = parser.isoparse(spPost["data_modificacao"]).replace(microsecond=0)

            if dateOpensearch < dateSpPost:
                return {"status": 1, "id": opensearchData["id"]}
            else:
                return {"status": 3, "id": opensearchData["id"]}

    return {"status": 1, "id": None}

def kbSend(kbPost, urlContentAddress):
    content = get_only_texts(kbPost['content']['html'])
    content = ' '.join(content.split())[:1000]

    contextTextImagePdf = get_text_with_images_and_pdf(kbPost['content']['html'])
    contextTextImagePdf = ' '.join(contextTextImagePdf.split())

    payload = {
       'id': kbPost['metadata']['id'],
       'mbtype': 'manual',
       'url': kbPost['metadata']['url'],
       'area': get_tags_from_kb(kbPost['metadata']['category']['slug'], 'area'),
       'theme': get_tags_from_kb(kbPost['metadata']['category']['slug'], 'theme'),
       'functiontags': [],
       'otherTags': [],
       'notify': "false",
       'content_tags': [],
       'publication_date': kbPost['metadata']['dates']['modified'],
       'modification_date': kbPost['metadata']['dates']['modified'],
       'openInNewTab': True,
       'image': '',
       'highlights': "false",
       'buttonText': '',
       'description': content,
       'abstract': content,
       'html': urlContentAddress
    }
    payload = {key: value for key, value in payload.items() if value not in (None, '', [], {})}

    print('Payload a ser enviado para o OpenSearch:', json.dumps(payload, ensure_ascii=False, indent=2))

    print('external_id:', kbPost['metadata']['id'])
    print('title:', kbPost['metadata']['title'])
    print('text:', contextTextImagePdf)

    document = build_document(
        external_id=kbPost['metadata']['id'],
        title=kbPost['metadata']['title'],
        text=contextTextImagePdf,
        payload=payload,
    )
    request_body = {'documents': [document]}

    url = get_upsert_url(DATA_IN_USE['host'])

    response = requests.post(
        url,
        json=request_body,
        headers=get_headers(DATA_IN_USE['api_key']),
        timeout=DATA_IN_USE['timeout'],
    )
    response.raise_for_status()
    print('Manual enviado com sucesso:', response.status_code, response.text, response.json(), json.dumps(request_body))

    return document