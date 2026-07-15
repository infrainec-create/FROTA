"""Analista de manutenção com a Responses API."""
from __future__ import annotations

import json
from typing import Any

from openai import OpenAI


def analyze_maintenance(api_key: str, vehicle: dict[str, Any], maintenance: list[dict[str, Any]], fuel: list[dict[str, Any]]) -> str:
    """Gera um parecer de apoio; nunca toma decisões operacionais automaticamente."""
    context = json.dumps(
        {"veiculo": vehicle, "manutencoes": maintenance[-20:], "abastecimentos": fuel[-20:]},
        ensure_ascii=False,
        default=str,
    )
    response = OpenAI(api_key=api_key).chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "Você é um analista de manutenção de frota. Responda em português do Brasil, "
                    "usando somente os registros recebidos. Avalie padrões de custo, frequência e "
                    "quilometragem; priorize riscos em Crítico, Atenção ou Monitorar e dê ações objetivas. "
                    "Não invente falhas ou dados. Informe incertezas. Termine com: 'Este parecer é apoio "
                    "à decisão e não substitui a inspeção de um profissional qualificado.'"
                )
            },
            {
                "role": "user",
                "content": f"Analise os dados desta frota/veículo:\n{context}"
            }
        ]
    )
    return response.choices[0].message.content or ""
