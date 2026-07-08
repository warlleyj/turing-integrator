import tools.aem as aem
import tools.opensearch as opensearch
import time
from dateutil import parser
import datetime
from zoneinfo import ZoneInfo
import requests

SEND_BATCH_SIZE = 100

def bool_to_string(value):
    if isinstance(value, str):
        return 'true' if value.strip().lower() == 'true' else 'false'
    return 'true' if value is True else 'false'

def url_is_valid(url):
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/126.0 Safari/537.36"
        )
    }

    try:
        response = requests.get(url, headers=headers, allow_redirects=True, stream=True, timeout=10)

        # Considera válida se retornou 200–399
        if 200 <= response.status_code < 400:
            return True
        else:
            return False

    except requests.RequestException as e:
        # opcional: logar o erro
        print(f"Erro ao verificar {url}: {e}")
        return False

def converter_data(data_str):
    if not data_str:
        return ''
    dt = parser.parse(data_str).replace(tzinfo=None)
    # dt = dt + datetime.timedelta(hours=3)
    return dt.strftime('%Y-%m-%dT%H:%M:%S') + '+00:00'


def safe_send(sp_post, mbtype):
    try:
        opensearch.send(sp_post, mbtype)
        return True
    except Exception as e:
        print(
            f"Erro ao enviar para OpenSearch. tipo={mbtype} id={sp_post.get('id', 'sem-id')} erro={e}"
        )
        return False

def main():
    params = {
        "type": "dam:Asset",
        "property": "jcr:content/cq:lastReplicationAction",
        "property.value": "Activate",
        "p.limit": "-1",
        "orderby": "path"
    }

    allContentFragment = aem.getAllContentFragment(params)
    allPostsOpensearch = opensearch.getAllOpenSearchIds('post')
    newsletter_sent_count = 0

    for contentFragment in allContentFragment:
        id = contentFragment['path']
        if aem.isNewsletter(id):
            proprieties = aem.getContentFragmentProprieties(id, params)
            pageContent = aem.getPageContent(id)
            originProprieties = aem.getOriginProprieties(id, params)
            if proprieties and proprieties.get('title') and pageContent:
                contentFragment['lastModified'] = pageContent['lastModifiedDate']
                integration = aem.integrationStatus(allPostsOpensearch, contentFragment)

                allPostsOpensearch = [
                    ds for ds in allPostsOpensearch
                    if ds["id"] != integration['id']
                ]

                match integration['status']:
                    case 1:
                        if newsletter_sent_count >= SEND_BATCH_SIZE:
                            continue

                        textContent = aem.find_all_objects(pageContent)

                        dt = parser.parse(originProprieties.get('jcr:created'))

                        spPost = {
                            'id': id,
                            't': proprieties.get('title'),
                            'abstract': '',
                            'm': " - ".join(textContent),
                            'pathFragment': aem.getPathByName(contentFragment['name'], 'posts/posts-newsletter'),
                            'tagFragmentArea': proprieties.get('area', False),
                            'tagFragmentTheme': proprieties.get('theme', False),
                            'categoryIds': [],
                            'lastActivityAt': contentFragment['lastModified'],
                            'publicationDate': dt.isoformat(),
                            'image': proprieties.get('banner', ''),
                            'highlights': bool_to_string(proprieties.get('highlights', False))
                        }

                        safe_send(spPost, 'post')
                        newsletter_sent_count += 1

    params = {
        "path": "/content/maple-bear/posts",
        "type": "cq:Page",
        "property": "jcr:content/cq:lastReplicationAction",
        "property.value": "Activate",
        "p.limit": "-1",
        "orderby": "path"
    }

    allContentFragment = aem.getAllContentFragment(params)
    posts_sent_count = 0

    for contentFragment in allContentFragment:
        id = contentFragment['path']
        if aem.isPost(id):
            proprieties = aem.getContentFragmentProprieties(id, params)
            pageContent = aem.getPageContent(id)
            originProprieties = aem.getOriginProprieties(id, params)
            if proprieties and proprieties.get('title') and pageContent:
                contentFragment['lastModified'] = pageContent['lastModifiedDate']
                integration = aem.integrationStatus(allPostsOpensearch, contentFragment)

                allPostsOpensearch = [
                    ds for ds in allPostsOpensearch
                    if ds["id"] != integration['id']
                ]

                match integration['status']:
                    case 1:
                        if posts_sent_count >= SEND_BATCH_SIZE:
                            continue

                        textContent = aem.find_all_objects(pageContent)

                        dt = parser.parse(originProprieties.get('jcr:created'))

                        spPost = {
                            'id': id,
                            't': proprieties.get('title'),
                            'abstract': proprieties.get('content', ''),
                            'm': " - ".join(textContent),
                            'pathFragment': aem.getPathByName(contentFragment['name']),
                            'tagFragmentArea': proprieties.get('area', False),
                            'tagFragmentTheme': proprieties.get('theme', False),
                            'categoryIds': [],
                            'lastActivityAt': contentFragment['lastModified'],
                            'publicationDate': dt.isoformat(),
                            'image': proprieties.get('banner', ''),
                            'highlights': bool_to_string(proprieties.get('highlights', False))
                        }

                        safe_send(spPost, 'post')
                        posts_sent_count += 1


    params = {
        "type": "dam:Asset",
        "property": "jcr:content/cq:lastReplicationAction",
        "property.value": "Activate",
        "p.limit": "-1",
        "orderby": "path"
    }

    allContentFragment = aem.getAllContentFragment(params)
    allEventsOpensearch = opensearch.getAllOpenSearchIds('event')
    events_sent_count = 0

    for contentFragment in allContentFragment:
        id = contentFragment['path']
        if aem.isEvent(id):
            proprieties = aem.getContentFragmentProprieties(id, params)
            originProprieties = aem.getOriginProprieties(id, params)
            if proprieties and proprieties.get('title') and proprieties.get('title'):
                dt = datetime.datetime.strptime(contentFragment.get('lastModified', '2020-01-01 17:28:58'), "%Y-%m-%d %H:%M:%S")
                contentFragment['lastModified'] = int(dt.timestamp() * 1000)

                integration = aem.integrationStatus(allEventsOpensearch, contentFragment)

                allEventsOpensearch = [
                    ds for ds in allEventsOpensearch
                    if ds["id"] != integration['id']
                ]

                match integration['status']:
                    case 1:
                        if events_sent_count >= SEND_BATCH_SIZE:
                            continue

                        dt = parser.parse(originProprieties.get('jcr:created'))

                        spPost = {
                            'id': id,
                            't': proprieties.get('title'),
                            'abstract': '',
                            'm': '',
                            'pathFragment': aem.getPathByName(contentFragment['name'], 'events'),
                            'tagFragmentArea': [],
                            'tagFragmentTheme': [],
                            'categoryIds': [],
                            'lastActivityAt': contentFragment['lastModified'],
                            'publicationDate': dt.isoformat(),
                            'image': '',
                            'highlights': 'false',
                            'buttonTextFragment': proprieties.get('buttonText', 'Acesse aqui'),
                            'descriptionFragment': proprieties.get('description', ''),
                            'eventType': proprieties.get('eventType', []),
                            'allDay': proprieties.get('allDay', False) == 'true',
                            'buttonLink': proprieties.get('buttonLink', proprieties.get('local', '')),
                            'initialDate': converter_data(proprieties.get('initialDate', '')),
                            'finishDate': converter_data(proprieties.get('finishDate', ''))
                        }

                        spPost['m'] = f"<span>{str(proprieties.get('description', ''))}.</span>"

                        if proprieties.get('buttonLink', ''):
                            spPost['m'] += f"<span>link para acessar evento: {str(proprieties.get('buttonLink', ''))}.</span>"

                        # Obtém e formata a data inicial
                        initial_date_str = proprieties.get('initialDate', '')
                        try:
                            initial_date_fmt = parser.parse(initial_date_str).strftime('%d/%m/%Y %H:%M:%S') if initial_date_str else ''
                        except Exception:
                            initial_date_fmt = initial_date_str

                        # Obtém e formata a data final
                        finish_date_str = proprieties.get('finishDate', '')
                        try:
                            finish_date_fmt = parser.parse(finish_date_str).strftime('%d/%m/%Y %H:%M:%S') if finish_date_str else ''
                        except Exception:
                            finish_date_fmt = finish_date_str

                        spPost['m'] += f"<span>Data Inicial: {initial_date_fmt}.</span>"
                        spPost['m'] += f"<span>Data Final: {finish_date_fmt}.</span>"

                        if spPost['allDay']:
                            spPost['m'] += "<span>Evento o dia todo.</span>"

                        data_final = parser.parse(finish_date_str) if finish_date_str else None
                        agora = datetime.datetime.now(data_final.tzinfo) if data_final and data_final.tzinfo else datetime.datetime.now()
                        if data_final:
                            if data_final < agora:
                                spPost['m'] += "<span>Evento já aconteceu.</span>"
                            else:
                                spPost['m'] += "<span>Evento ainda vai acontecer.</span>"
                        safe_send(spPost, 'event')
                        events_sent_count += 1

    for postOpensearch in allPostsOpensearch[:100]:
        if "maplebear.activehosted.com" not in postOpensearch['id']:
            opensearch.delete(postOpensearch['id'], True)
        else:
           if url_is_valid(postOpensearch['id']) is False:
               opensearch.delete(postOpensearch['id'], True)

    for eventOpensearch in allEventsOpensearch[:100]:
          opensearch.delete(eventOpensearch['id'], False)

if __name__ == '__main__':
    main()
