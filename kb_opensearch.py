import tools.opensearch as opensearch
import tools.kb as kb

def main():

    allManualsOpensearch = opensearch.getAllOpenSearchIds('manual')

    kbPosts = kb.getPosts()

    for kbPost in kbPosts:
        integration = opensearch.integrationStatus(allManualsOpensearch, kbPost)

        allManualsOpensearch = [
            ds for ds in allManualsOpensearch
            if ds["id"] != integration['id']
        ]

        match integration['status']:
            case 1:
                urlRenderAddress = kbPost['url_body_content']
                kbPost = kb.getPostDetails(kbPost)
                opensearch.kbSend(kbPost, urlRenderAddress)

    for manualOpensearchToDelete in allManualsOpensearch[:1]:
        opensearch.delete(manualOpensearchToDelete['id'], True)
        

if __name__ == '__main__':
    main()