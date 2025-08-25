#!/usr/bin/env python3
"""
Azure OpenAI 연결 테스트 스크립트
사용법: python test_azure_openai.py
"""

import os
import time
import logging
from openai import AzureOpenAI

# .env 파일 로드
try:
    from dotenv import load_dotenv
    load_dotenv()
    print("✅ .env 파일 로드됨")
except ImportError:
    print("⚠️  python-dotenv 없음, .env 파일 수동 로드")
    # .env 파일을 수동으로 로드
    try:
        with open('.env', 'r') as f:
            for line in f:
                if '=' in line and not line.strip().startswith('#'):
                    key, value = line.strip().split('=', 1)
                    os.environ[key] = value
        print("✅ .env 파일 수동 로드 완료")
    except FileNotFoundError:
        print("❌ .env 파일을 찾을 수 없습니다")

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_azure_openai():
    """Azure OpenAI 연결 및 번역 테스트"""
    
    print("🔍 Azure OpenAI 연결 테스트 시작")
    print("=" * 50)
    
    # 1. 환경 변수 확인
    print("\n📋 환경 변수 확인:")
    api_key = os.getenv('AZURE_OPENAI_API_KEY')
    endpoint = os.getenv('AZURE_OPENAI_ENDPOINT')
    api_version = os.getenv('AZURE_OPENAI_API_VERSION', '2024-12-01-preview')
    deployment_name = os.getenv('AZURE_OPENAI_DEPLOYMENT_NAME')
    
    print(f"   API_KEY: {'✅ 설정됨' if api_key else '❌ 없음'}")
    print(f"   ENDPOINT: {endpoint if endpoint else '❌ 없음'}")
    print(f"   API_VERSION: {api_version}")
    print(f"   DEPLOYMENT: {deployment_name if deployment_name else '❌ 없음'}")
    
    if not all([api_key, endpoint, deployment_name]):
        print("\n❌ 필수 환경 변수가 설정되지 않았습니다!")
        print("다음 환경 변수를 설정해주세요:")
        print("  - AZURE_OPENAI_API_KEY")
        print("  - AZURE_OPENAI_ENDPOINT")
        print("  - AZURE_OPENAI_DEPLOYMENT_NAME")
        return False
    
    # 2. 클라이언트 초기화
    print("\n🔧 Azure OpenAI 클라이언트 초기화:")
    try:
        client = AzureOpenAI(
            api_version=api_version,
            azure_endpoint=endpoint,
            api_key=api_key
        )
        print("   ✅ 클라이언트 초기화 성공")
    except Exception as e:
        print(f"   ❌ 클라이언트 초기화 실패: {e}")
        return False
    
    # 3. 번역 테스트 데이터
    test_cases = [
        ("슬랙 봇 이벤트 처리에서는 “Delayed Response” 패턴슬랙 이벤트 API도 응답까지 3초 제한이 있습니다. Event 수신 후 즉시 200 OK, 실질적인 후처리는 비동기로 처리하여 슬랙 Web API(chat.postMessage 등)로 추가 메시지를 보낼 수 있습니다.", "ko"),

    ]
    
    # 4. 각 테스트 케이스 실행
    for i, (text, source_lang) in enumerate(test_cases, 1):
        print(f"\n🧪 테스트 케이스 {i}: '{text}' ({source_lang})")
        print("-" * 30)
        
        if source_lang == 'ko':
            prompt = f"Translate to English:\n{text}"
        else:
            prompt = f"Translate to Korean:\n{text}"
        
        print(f"   프롬프트: {prompt}")
        print(f"   모델: {deployment_name}")
        
        # 다양한 타임아웃으로 테스트
        timeouts = [30]
        
        for timeout in timeouts:
            print(f"\n   ⏱️  타임아웃 {timeout}초로 테스트:")
            
            try:
                start_time = time.time()
                
                response = client.chat.completions.create(
                    messages=[
                        {
                            "role": "system",
                            "content": "You are a professional translator. Translate accurately and naturally. When translating to Korean, always use formal/polite language (존댓말) with appropriate honorific forms (-요, -다, etc.). Only return the translation."
                        },
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    max_completion_tokens=1000,
                    model=deployment_name,
                    timeout=timeout
                )
                
                end_time = time.time()
                duration = end_time - start_time
                
                # 응답 구조 상세 분석
                print(f"      ✅ 응답 받음! ({duration:.2f}초)")
                print(f"      🔍 응답 구조 분석:")
                print(f"         - response type: {type(response)}")
                print(f"         - choices 개수: {len(response.choices)}")
                print(f"         - choice[0] type: {type(response.choices[0])}")
                print(f"         - message type: {type(response.choices[0].message)}")
                print(f"         - content type: {type(response.choices[0].message.content)}")
                
                translated_text = response.choices[0].message.content
                print(f"         - raw content: '{translated_text}'")
                
                if translated_text:
                    translated_text = translated_text.strip()
                else:
                    translated_text = "[EMPTY]"
                
                print(f"      📝 번역 결과: '{translated_text}'")
                print(f"      📊 응답 길이: {len(translated_text)} 글자")
                
                # 전체 응답도 출력해보기
                print(f"      🌐 전체 응답:")
                print(f"         {response}")
                
                # 첫 번째 성공하면 다음 타임아웃은 건너뛰기
                break
                
            except Exception as e:
                print(f"      ❌ 실패 (타임아웃 {timeout}초): {e}")
                print(f"      🔍 에러 타입: {type(e).__name__}")
                
                if timeout == timeouts[-1]:  # 마지막 타임아웃도 실패
                    print(f"      💀 모든 타임아웃 설정에서 실패")
    
    print(f"\n{'='*50}")
    print("🏁 Azure OpenAI 테스트 완료")
    return True

def test_environment_only():
    """환경 변수만 빠르게 테스트"""
    print("\n🔍 환경 변수 확인:")
    
    required_vars = [
        'AZURE_OPENAI_API_KEY',
        'AZURE_OPENAI_ENDPOINT', 
        'AZURE_OPENAI_DEPLOYMENT_NAME'
    ]
    
    all_set = True
    for var in required_vars:
        value = os.getenv(var)
        status = "✅ 설정됨" if value else "❌ 없음"
        masked_value = value[:10] + "..." if value and len(value) > 10 else value
        print(f"   {var}: {status} ({masked_value if value else ''})")
        if not value:
            all_set = False
    
    return all_set

if __name__ == "__main__":
    print("🚀 Azure OpenAI 테스트 스크립트")
    print("사용법: python test_azure_openai.py [--env-only]")
    
    import sys
    if '--env-only' in sys.argv:
        test_environment_only()
    else:
        test_azure_openai()