"""Analista de manutenção com a Responses API."""
from __future__ import annotations

import json
from typing import Any

from openai import OpenAI


def analyze_maintenance(
    api_key: str,
    vehicle: dict[str, Any] | None,
    maintenance: list[dict[str, Any]],
    fuel: list[dict[str, Any]],
    mode: str = "general",
    vehicles_list: list[dict[str, Any]] | None = None,
    expenses: list[dict[str, Any]] | None = None,
    provider: str = "openai"
) -> str:
    """Gera um parecer de apoio ou previsão orçamentária; nunca toma decisões operacionais automaticamente."""
    if vehicle is None:
        # Fleet-wide analysis
        context = json.dumps(
            {
                "frota_veiculos": vehicles_list if vehicles_list else [],
                "manutencoes_recentes": maintenance[-50:],
                "abastecimentos_recentes": fuel[-50:],
                "outras_despesas_recentes": expenses[-50:] if expenses else []
            },
            ensure_ascii=False,
            default=str,
        )
        if mode == "budget":
            system_content = (
                "Você é um especialista em planejamento financeiro e orçamento de frotas corporativas. "
                "Com base no histórico recente de toda a frota de veículos (abastecimentos, manutenções e outras despesas operacionais como pedágios, estacionamentos e lavagens), "
                "projete o orçamento estimado para o PRÓXIMO MÊS de toda a frota de forma consolidada. "
                "Responda em português do Brasil. Divida a estimativa por categorias (Combustível, Manutenção, Outros), "
                "aponte possíveis desvios orçamentários, e sugira 3 ações estratégicas corporativas para redução de custos. "
                "Formate de maneira elegante utilizando tabelas em markdown. "
                "Termine com: 'Esta projeção orçamentária é baseada em dados estatísticos passados e estimativas de mercado da frota.'"
            )
        else:
            system_content = (
                "Você é um analista de manutenção de frota corporativa. Responda em português do Brasil. "
                "Avalie padrões de custo, frequência de manutenção de toda a frota de forma consolidada, considerando também custos extras/diversos. "
                "Aponte quais veículos ou tipos de despesa representam maior risco de custo ou paradas operacionais. "
                "Classifique os riscos de frota em Crítico, Atenção ou Monitorar e forneça ações objetivas. "
                "Não invente dados. Termine com: 'Este parecer é apoio à decisão de frota e não substitui a inspeção técnica individual de profissionais.'"
            )
    else:
        # Single vehicle analysis
        context = json.dumps(
            {
                "veiculo": vehicle, 
                "manutencoes": maintenance[-20:], 
                "abastecimentos": fuel[-20:],
                "outras_despesas": expenses[-20:] if expenses else []
            },
            ensure_ascii=False,
            default=str,
        )
        
        if mode == "budget":
            system_content = (
                "Você é um especialista em planejamento financeiro e orçamento de frotas. "
                "Com base no histórico de custos de combustível, manutenção e outras despesas fornecidos, projete "
                "o orçamento estimado para o PRÓXIMO MÊS deste veículo. Responda em português do Brasil. "
                "Divida a estimativa por categorias (Combustível, Manutenção, Outros), aponte possíveis riscos orçamentários "
                "e sugira 3 ações práticas de redução de custos. Formate de maneira elegante utilizando tabelas em markdown. "
                "Termine com: 'Esta projeção orçamentária é baseada em dados estatísticos passados e estimativas de mercado.'"
            )
        else:
            system_content = (
                "Você é um analista de manutenção de frota. Responda em português do Brasil, "
                "usando somente os registros recebidos. Avalie padrões de custo, frequência, despesas extras e "
                "quilometragem; priorize riscos em Crítico, Atenção ou Monitorar e dê ações objetivas. "
                "Não invente falhas ou dados. Informe incertezas. Termine com: 'Este parecer é apoio "
                "à decisão e não substitui a inspeção de um profissional qualificado.'"
            )

    if provider == "gemini":
        client = OpenAI(
            api_key=api_key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
        )
        model_name = "gemini-1.5-flash"
    else:
        client = OpenAI(api_key=api_key)
        model_name = "gpt-4o-mini"

    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {
                "role": "system",
                "content": system_content
            },
            {
                "role": "user",
                "content": f"Analise os dados desta frota/veículo:\n{context}"
            }
        ]
    )
    return response.choices[0].message.content or ""
