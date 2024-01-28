from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import viewsets
from rest_framework import status

from django.shortcuts import redirect

import asyncio

import json
import os

from .scrapers import ScraperUtil
from .validators import URLQueryStringParameterValidator

from .services import JournalJsonArrayOfDOUService, DetailSingleJournalOfDOUService

from polls.serializers import JournalJsonArrayOfDOUSerializer, DetailSingleJournalOfDOUSerializer
from polls.models import JournalJsonArrayOfDOU, DetailSingleJournalOfDOU
from polls.services import JournalJsonArrayOfDOUService, DetailSingleJournalOfDOUService

from polls.utils import DateUtil

from django_celery_example.celery import run_scraper_with_all_params_task

from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor

URL_MAIN_API_DJANGOAPP=os.getenv('URL_MAIN_API_DJANGOAPP', 
                                    'http://127.0.0.1:8010/',) 

class ScraperViewSet(APIView):
    def get(self, request):
        
        secaoURLQueryString = request.GET.get('secao')
        dataURLQueryString = request.GET.get('data')
        
        saveInDBFlag = request.GET.get('saveInDBFlag')
        
        detailSingleDOUJournalWithUrlTitleFieldURLQueryString = request.GET.get('detailSingleDOUJournalWithUrlTitleField')

        detailDOUJournalFlag = request.GET.get('detailDOUJournalFlag')
        
        balancerFlag = request.GET.get('balancerFlag')
        
        
        
        if detailDOUJournalFlag:
            detailDOUJournalFlag = True
            
        if balancerFlag:
            balancerFlag = True
            
        # Se não existem parâmetros
        # Lembrando que se trata dos parâmetros: secaoURLQueryString, dataURLQueryString e detailSingleDOUJournalWithUrlTitleFieldURLQueryString
        # NÃO se trata das flags: saveInDBFlag e detailDOUJournalFlag.
        # Essas flags modificam o comportamento desses handlers abaixo.
        if URLQueryStringParameterValidator.is_empty_params(secaoURLQueryString, 
                                                            dataURLQueryString, 
                                                            detailSingleDOUJournalWithUrlTitleFieldURLQueryString):
            
            return self.handle_URL_empty_params(saveInDBFlag, detailDOUJournalFlag, balancerFlag)
            
        # Se ?section= e ?data= foi passado no URL query string param
        if (URLQueryStringParameterValidator.is_secaoURLQueryString_and_dataURLQueryString_params(secaoURLQueryString, 
                                                                                                    dataURLQueryString) and \
              URLQueryStringParameterValidator.is_secaoURLQueryString_and_dataURLQueryString_valid(secaoURLQueryString, 
                                                                                                      dataURLQueryString)):
            print("MAIS UM GET PARA: " + secaoURLQueryString)
            
            return self.handle_balancer_secaoURLQueryString_and_dataURLQueryString_params(secaoURLQueryString, 
                                                                                dataURLQueryString, 
                                                                                saveInDBFlag,
                                                                                detailDOUJournalFlag, 
                                                                                balancerFlag)
        
            
    # Utilizado para balancear as cargas de listas de url para raspagem,
    # recebe uma lista com a mesma quantidade de urls para cada instância da API:  
    # recebe apenas o field `urlTitle` na lista, faz a concatecanção com a DOU_DETAIL_SINGLE_RECORD_URL
    def post(self, request, *args, **kwargs):
        try:
            json_data = json.loads(request.body)
            
        except json.JSONDecodeError:
            return Response({'error': 'Dados JSON inválidos'}, status=400)
        
        data_json_list = json_data.get('urlTitleList', [])
        # details_list = ScraperUtil.run_detail_single_dou_record_scraper_using_event_loop(data_json_list)
        
        
        sites_list = asyncio.run(ScraperUtil.run_make_requests_to_detail_dou_journal_using_asyncio_gather_with_urlsTitleList(data_json_list))

         # Verificações das urls que deu != 200 para retentativas até conseguir tudo
        # Enquanto status code != 200 realizamos requisições nas Fails Urls
        fails_urls_list = []
        success_sites_list = []
        while True:

            for site in sites_list:
                if site.status_code != 200:
                    fails_urls_list.append(site.url)
                    print(f"\033[31mRetrying para: " + site.url[35:] + "\033[0m") # https://www.in.gov.br/en/web/dou/-/
                else: 
                    success_sites_list.append(site)

            if len(fails_urls_list) == 0:
                break
            
            print("\n\nTOTAL DE RETRY: ", len(fails_urls_list))
            print("\n\nGERANDO SUMARIO....\n\n")
            self.gerar_sumario(sites_list)
            
            sites_list = asyncio.run(ScraperUtil.run_retrying_make_requests_to_detail_dou_journal_using_asyncio_gather_with_urlsFailList(fails_urls_list))
            fails_urls_list = []
            
        details_list = ScraperUtil.run_scraper_detail_dou_journal_using_event_loop(success_sites_list, data_json_list)
        

        return self.handle_response_and_when_saveInDBFlag_is_true_save(details_list)
    
    
    
    def gerar_sumario(self, responses):
        # Dicionários para contar as ocorrências de status codes e mensagens
        contador_status_code = {}
        contador_mensagens = {}

        # Itera sobre as respostas e incrementa os contadores
        for response in responses:
            status_code = response.status_code if hasattr(response, 'status_code') else None
            mensagem = response.content if hasattr(response, 'content') and response.status_code == 503 else None

            # Contagem de status codes
            if status_code is not None:
                if status_code in contador_status_code:
                    contador_status_code[status_code] += 1
                else:
                    contador_status_code[status_code] = 1

            # Contagem de mensagens
            if mensagem is not None:
                if mensagem in contador_mensagens:
                    contador_mensagens[mensagem] += 1
                else:
                    contador_mensagens[mensagem] = 1

        # Imprime o sumário de status codes
        print("Sumário de Status Codes:")
        for status_code, contagem in contador_status_code.items():
            print(f"Status Code {status_code}: {contagem} ocorrência(s)")

        # Imprime o sumário de mensagens
        print("\nSumário de Mensagens:")
        for mensagem, contagem in contador_mensagens.items():
            print(f"Mensagem: {mensagem}: {contagem} ocorrência(s)")
    
        
    # --------------------- [ Handlers área ] ---------------------
    
    
     # Lida com as responses dos handlers abaixo, evitando repetição de cod
    def handle_response_and_when_saveInDBFlag_is_true_save(self, response, 
                                                           saveInDBFlag : bool, 
                                                           detailDOUJournalFlag : bool):
        
        if isinstance(response, list):
            
            if saveInDBFlag:
                
                if detailDOUJournalFlag:
                    
                    print("DETAILS OBJECT SENDO INSERIDO NO BANCO....")
                    
                    with ProcessPoolExecutor() as executor:
    
                        executor.map(DetailSingleJournalOfDOUService.insert_into_distinct_journals_and_date_normalize, [response])
                
                    # Como salvou no banco, é melhor redirecionar para a rota da API que consulta a prórpia API do banco
                    # Pois a depender da quantidade de dados, quando não utilizar a flag de salvar, 
                    # toda a massa de dados é retornarda para o cliente, desta forma demora muito para renderizar o DOM
                    # Já a API do banco retorna os dados com paginação, assim não sobrecarrega o DOM.
                    return redirect(URL_MAIN_API_DJANGOAPP + 'db_dou_api/detailsinglejournalofdouviewset/')

                else:
                    
                    with ProcessPoolExecutor() as executor:
        
                        executor.map(JournalJsonArrayOfDOUService.insert_into_distinct_journals_and_date_normalize, [response])
                
                    # Como salvou no banco, é melhor redirecionar para a rota da API que consulta a prórpia API do banco
                    # Pois a depender da quantidade de dados, quando não utilizar a flag de salvar, 
                    # toda a massa de dados é retornarda para o cliente, desta forma demora muito para renderizar o DOM
                    # Já a API do banco retorna os dados com paginação, assim não sobrecarrega o DOM.
                    return redirect(URL_MAIN_API_DJANGOAPP + 'db_dou_api/journaljsonarrayofdouviewset/')

        elif isinstance(response, dict):
        
            if 'error_in_our_server_side' in response:
                
                return Response(response, status=status.HTTP_400_BAD_REQUEST)
            
            elif 'jsonArray_isEmpty' in response:
                
                return Response(response, status=status.HTTP_404_NOT_FOUND)
            
            elif 'error_in_dou_server_side' in response:
                
                return Response(response, status=status.HTTP_500_BAD_REQUEST)
        
            elif saveInDBFlag:

                if detailDOUJournalFlag:
                    
                    print("DETAILS OBJECT SENDO INSERIDO NO BANCO....")

                else:
                    
                    with ProcessPoolExecutor() as executor:
        
                        executor.map(JournalJsonArrayOfDOUService.insert_into_distinct_journals_and_date_normalize, [response])
                
                    # Como salvou no banco, é melhor redirecionar para a rota da API que consulta a prórpia API do banco
                    # Pois a depender da quantidade de dados, quando não utilizar a flag de salvar, 
                    # toda a massa de dados é retornarda para o cliente, desta forma demora muito para renderizar o DOM
                    # Já a API do banco retorna os dados com paginação, assim não sobrecarrega o DOM.
                    return redirect(URL_MAIN_API_DJANGOAPP + 'db_dou_api/journaljsonarrayofdouviewset/')
            
        return Response(response)
        
    
    # Varre tudo da home do https://www.in.gov.br/leiturajornal
    # - GET http://127.0.0.1:8000/trigger_web_scraping_dou_api/ 
    
    # Varre tudo da home do https://www.in.gov.br/leiturajornal e detalha todos dou do dia
    # - GET http://127.0.0.1:8000/trigger_web_scraping_dou_api/?detailDOUJournalFlag=True
    def handle_URL_empty_params(self, saveInDBFlag : bool, 
                                detailDOUJournalFlag : bool,
                                balancerFlag : bool):
        
        # response = ScraperUtil.run_scraper_with_empty_params_using_clone_instances(detailDOUJournalFlag, balancerFlag)
        
        # Criar uma lista de argumentos para suas tarefas

        dous_list = ['do1', 'do2', 'do3']
        data = DateUtil.get_current_date_db_and_brazilian_format()
        

        # Criar uma função para chamar a tarefa
        def call_my_task(secao, data, detailDOUJournalFlag, balancerFlag):
            
            result_future_with_celery = run_scraper_with_all_params_task.delay(secao, 
                                                                               data, 
                                                                               detailDOUJournalFlag, 
                                                                               balancerFlag,
                                                                               saveInDBFlag)
        
            if not result_future_with_celery.ready():

                print("Tarefa sendo processada nos wrokers, em breve finaliza...") 
                
                if detailDOUJournalFlag:
                          
                    print("Para visualizar a tarefa finalizada: http://127.0.0.1:8010/db_dou_api/detailsinglejournalofdouviewset/")  
                        
                else:
                    
                    print("Para visualizar a tarefa finalizada: http://127.0.0.1:8010/db_dou_api/journaljsonarrayofdouviewset/")    
                    
                    
            result = result_future_with_celery.get()
            
            return result
        
        
        # Usar ThreadPoolExecutor para executar as tarefas em paralelo
        with ThreadPoolExecutor() as executor:
            result = list(executor.map(call_my_task, dous_list, 
                                                     [data]*len(dous_list), 
                                                     [detailDOUJournalFlag]*len(dous_list),
                                                     [balancerFlag]*len(dous_list)))

        
        return self.handle_response_and_when_saveInDBFlag_is_true_save(result, saveInDBFlag, detailDOUJournalFlag)
        
    
    # Varre os DOU da seção e data mencionada no query string param
    # - GET http://127.0.0.1:8000/trigger_web_scraping_dou_api/?secao=`do1 | do2 | do3`&data=`DD-MM-AAAA`
    # E Detalha cada jornal
    def handle_balancer_secaoURLQueryString_and_dataURLQueryString_params(self, secaoURLQueryString : str, 
                                                                 dataURLQueryString : str,
                                                                 saveInDBFlag : bool,
                                                                 detailDOUJournalFlag : bool,
                                                                 balancerFlag : bool):
        
        # response = ScraperUtil.run_scraper_with_all_params(secaoURLQueryString, dataURLQueryString, detailDOUJournalFlag, balancerFlag)

        result_future_with_celery = run_scraper_with_all_params_task.delay(secaoURLQueryString, 
                                                                           dataURLQueryString, 
                                                                           detailDOUJournalFlag, 
                                                                           balancerFlag, saveInDBFlag)

        while not result_future_with_celery.ready():

            print("Tarefa sendo processada nos wrokers...")            

        result = result_future_with_celery.get()
        return self.handle_response_and_when_saveInDBFlag_is_true_save(result, saveInDBFlag, detailDOUJournalFlag)
    
    
    
# ENDPOINT PARA A BASE DE DADOS LOCAL DO jsonArray: 

# http://127.0.0.1:8000/db_dou_api/journaljsonarrayofdouviewset/?page=320

# Obtido no portal https://www.in.gov.br/leiturajornal:
# scriptTag = document.querySelectorAll("#params")[0]
# scriptTagTextContent = scriptTag.textContent 
# var jsonObj = JSON.parse(scriptTagTextContent);
class JournalJsonArrayOfDOUViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows JsonArrayOfDOU to be viewed or edited.
    """
    queryset = JournalJsonArrayOfDOU.objects.all()
    serializer_class = JournalJsonArrayOfDOUSerializer
    
    
    
# ENDPOINT PARA A BASE DE DADOS LOCAL DOS JORNAIS DETALHADOS: 

# http://127.0.0.1:8000/db_dou_api/journaljsonarrayofdouviewset/?page=320

class DetailSingleJournalOfDOUViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows DetailSingleJournalOfDOU to be viewed or edited.
    """
    queryset = DetailSingleJournalOfDOU.objects.all()
    serializer_class = DetailSingleJournalOfDOUSerializer