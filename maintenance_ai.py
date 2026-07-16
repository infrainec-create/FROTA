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
    vehicles_list: list[dict[str, Any]] | None = None
) -> str:
    """Gera um parecer de apoio ou previsão orçamentária; nunca toma decisões operacionais automaticamente."""
    if vehicle is None:
        # Fleet-wide analysis
        context = json.dumps(
            {
                "frota_veiculos": vehicles_list if vehicles_list else [],
                "manutencoes_recentes": maintenance[-50:],
                "abastecimentos_recentes": fuel[-50:]
            },
            ensure_ascii=False,
            default=str,
        )
        if mode == "budget":
            system_content = (
                "Você é um especialista em planejamento financeiro e orçamento de frotas corporativas. "
                "Com base no histórico recente de toda a frota de veículos (abastecimentos e manutenções), "
                "projete o orçamento estimado para o PRÓXIMO MÊS de toda a frota de forma consolidada. "
                "Responda em português do Brasil. Divida a estimativa por categorias (Combustível, Manutenção), "
                "aponte possíveis desvios orçamentários, e sugira 3 ações estratégicas corporativas para redução de custos. "
                "Formate de maneira elegante utilizando tabelas em markdown. "
                "Termine com: 'Esta projeção orçamentária é baseada em dados estatísticos passados e estimativas de mercado da frota.'"
            )
        else:
            system_content = (
                "Você é um analista de manutenção de frota corporativa. Responda em português do Brasil. "
                "Avalie padrões de custo, frequência de manutenção de toda a frota de forma consolidada. "
                "Aponte quais veículos ou tipos de manutenção representam maior risco de custo ou paradas operacionais. "
                "Classifique os riscos de frota em Crítico, Atenção ou Monitorar e forneça ações objetivas. "
                "Não invente dados. Termine com: 'Este parecer é apoio à decisão de frota e não substitui a inspeção técnica individual de profissionais.'"
            )
    else:
        # Single vehicle analysis
        context = json.dumps(
            {"veiculo": vehicle, "manutencoes": maintenance[-20:], "abastecimentos": fuel[-20:]},
            ensure_ascii=False,
            default=str,
        )
        
        if mode == "budget":
            system_content = (
                "Você é um especialista em planejamento financeiro e orçamento de frotas. "
                "Com base no histórico de custos de combustível e manutenção fornecidos, projete "
                "o orçamento estimado para o PRÓXIMO MÊS deste veículo. Responda em português do Brasil. "
                "Divida a estimativa por categorias (Combustível, Manutenção), aponte possíveis riscos orçamentários "
                "e sugira 3 ações práticas de redução de custos. Formate de maneira elegante utilizando tabelas em markdown. "
                "Termine com: 'Esta projeção orçamentária é baseada em dados estatísticos passados e estimativas de mercado.'"
            )
        else:
            system_content = (
                "Você é um analista de manutenção de frota. Responda em português do Brasil, "
                "usando somente os registros recebidos. Avalie padrões de custo, frequência e "
                "quilometragem; priorize riscos em Crítico, Atenção ou Monitorar e dê ações objetivas. "
                "Não invente falhas ou dados. Informe incertezas. Termine com: 'Este parecer é apoio "
                "à decisão e não substitui a inspeção de um profissional qualificado.'"
            )

    response = OpenAI(api_key=api_key).chat.completions.create(
        model="gpt-4o-mini",
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
