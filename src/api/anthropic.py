"""
پیاده‌سازی کلاینت Anthropic API (Claude)

این ماژول کلاینت Anthropic API را بر اساس مستندات API پیاده‌سازی می‌کند.
"""

import asyncio
import json
import time
import uuid
from typing import Any, Dict, List, Optional

import anthropic
from anthropic.types import MessageParam
from pydantic import ValidationError

from src.api.interfaces import (SentimentAnalysisResult,
                                            TextAnalysisClient,
                                            TextAnalysisRequest,
                                            TextAnalysisResponse,
                                            TopicExtractionResult)
from src.config.settings import settings
from src.core.exceptions import (AnthropicAPIError,
                                             ValidationError as AppValidationError)


class AnthropicClient(TextAnalysisClient):
    """پیاده‌سازی کلاینت Anthropic API"""
    
    def __init__(
        self, 
        api_key: str,
        default_model: str,
        fallback_model: str,
        max_tokens: int = 1024,
        temperature: float = 0.7
    ) -> None:
        self.api_key = api_key
        self.default_model = default_model
        self.fallback_model = fallback_model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.client = anthropic.Anthropic(api_key=api_key)
    
    async def _make_request(
        self, 
        system_prompt: str, 
        user_message: str,
        model: Optional[str] = None
    ) -> Dict[str, Any]:
        """ارسال درخواست به Anthropic API و دریافت پاسخ"""
        start_time = time.time()
        
        try:
            # استفاده از asyncio.to_thread برای اجرای درخواست همگام به صورت ناهمگام
            message = await asyncio.to_thread(
                self.client.messages.create,
                model=model or self.default_model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                system=system_prompt,
                messages=[
                    {"role": "user", "content": user_message}
                ]
            )
            
            # استخراج پاسخ
            response_text = message.content[0].text if message.content else ""
            
            # تلاش برای تبدیل پاسخ به JSON
            try:
                response_data = json.loads(response_text)
            except json.JSONDecodeError:
                # اگر پاسخ JSON معتبر نباشد، آن را به عنوان متن ساده برمی‌گردانیم
                response_data = {"text": response_text}
            
            # زمان پردازش
            processing_time = time.time() - start_time
            
            return {
                "data": response_data,
                "model": message.model,
                "processing_time": processing_time,
                "raw_response": message
            }
            
        except anthropic.APIError as e:
            # در صورت خطا با مدل پیش‌فرض، تلاش با مدل جایگزین
            if model is None and model != self.fallback_model:
                try:
                    return await self._make_request(system_prompt, user_message, self.fallback_model)
                except Exception as fallback_error:
                    raise AnthropicAPIError(
                        message=f"Anthropic API error (fallback failed): {str(fallback_error)}",
                        status_code=getattr(e, "status_code", None),
                        details={"original_error": str(e), "fallback_error": str(fallback_error)}
                    )
            else:
                raise AnthropicAPIError(
                    message=f"Anthropic API error: {str(e)}",
                    status_code=getattr(e, "status_code", None),
                    details={"error": str(e)}
                )
        except Exception as e:
            raise AnthropicAPIError(
                message=f"Unexpected error calling Anthropic API: {str(e)}",
                details={"error": str(e)}
            )
    
    async def analyze_text(self, request: TextAnalysisRequest) -> TextAnalysisResponse:
        """تحلیل متن با استفاده از API"""
        # تعیین نوع تحلیل
        if request.analysis_type == "sentiment":
            result = await self.sentiment_analysis(request.text)
            
        elif request.analysis_type == "topic":
            result = await self.topic_extraction(request.text)
            
        else:
            # تحلیل سفارشی
            system_prompt = f"""
            You are a text analysis assistant. Analyze the given text according to the requested analysis type: {request.analysis_type}.
            Provide your analysis in valid JSON format only. No explanation or additional text.
            """
            
            options_str = ""
            if request.options:
                options_str = f"\nOptions: {json.dumps(request.options, ensure_ascii=False)}"
            
            user_message = f"""
            Text to analyze: {request.text}
            
            Analysis type: {request.analysis_type}{options_str}
            
            Return ONLY valid JSON with your analysis results.
            """
            
            response = await self._make_request(system_prompt, user_message)
            
            try:
                # نتیجه تحلیل را با توجه به نوع آن برمی‌گردانیم
                result = response["data"]
            except (KeyError, ValueError) as e:
                raise AppValidationError(
                    message=f"Invalid analysis result: {str(e)}",
                    details={"response": response}
                )
        
        # ایجاد پاسخ تحلیل
        return TextAnalysisResponse(
            request_id=str(uuid.uuid4()),
            analysis_type=request.analysis_type,
            result=result,
            raw_response=None,  # برای امنیت و حریم خصوصی بیشتر
            processing_time=getattr(response, "processing_time", 0.0) if "response" in locals() else 0.0
        )
    
    async def sentiment_analysis(self, text: str) -> SentimentAnalysisResult:
        """تحلیل احساسات متن"""
        system_prompt = """
        You are a sentiment analysis assistant. Analyze the sentiment of the given text.
        Classify the sentiment as 'positive', 'neutral', or 'negative'.
        Provide confidence score between 0.0 and 1.0.
        Extract a relevant text snippet that justifies the sentiment.
        Return your analysis in the following JSON format:
        {
            "sentiment": "positive|neutral|negative",
            "confidence": 0.95,
            "text_snippet": "relevant text from the input that justifies the sentiment",
            "justification": "brief explanation of your sentiment classification"
        }
        Return ONLY the JSON without any other text or explanations.
        """
        
        user_message = f"""
        Text to analyze: {text}
        
        Perform sentiment analysis and return the JSON result.
        """
        
        response = await self._make_request(system_prompt, user_message)
        
        try:
            data = response["data"]
            return SentimentAnalysisResult(
                sentiment=data["sentiment"],
                confidence=data["confidence"],
                text_snippet=data["text_snippet"],
                justification=data.get("justification")
            )
        except (KeyError, ValidationError) as e:
            raise AppValidationError(
                message=f"Invalid sentiment analysis result: {str(e)}",
                details={"response": response}
            )
    
    async def topic_extraction(self, text: str) -> TopicExtractionResult:
        """استخراج موضوعات از متن"""
        system_prompt = """
        You are a topic extraction assistant. Extract the main topics from the given text.
        Identify 1-5 main topics depending on the text length and complexity.
        Assign a confidence value between 0.0 and 1.0 for each topic.
        Provide a brief summary of the overall content.
        Return your analysis in the following JSON format:
        {
            "topics": ["topic1", "topic2", "topic3"],
            "confidence": {"topic1": 0.95, "topic2": 0.85, "topic3": 0.78},
            "summary": "brief summary of the text content"
        }
        Return ONLY the JSON without any other text or explanations.
        """
        
        user_message = f"""
        Text to analyze: {text}
        
        Extract the main topics and return the JSON result.
        """
        
        response = await self._make_request(system_prompt, user_message)
        
        try:
            data = response["data"]
            return TopicExtractionResult(
                topics=data["topics"],
                confidence=data["confidence"],
                summary=data.get("summary")
            )
        except (KeyError, ValidationError) as e:
            raise AppValidationError(
                message=f"Invalid topic extraction result: {str(e)}",
                details={"response": response}
            )


def create_anthropic_client() -> AnthropicClient:
    """تابع سازنده برای ایجاد نمونه از کلاینت Anthropic"""
    return AnthropicClient(
        api_key=settings.anthropic_api.api_key,
        default_model=settings.anthropic_api.default_model,
        fallback_model=settings.anthropic_api.fallback_model,
        max_tokens=settings.anthropic_api.max_tokens,
        temperature=settings.anthropic_api.temperature
    )