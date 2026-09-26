"""Estado persistente: IDs já processados e IDs que falharam.

Fase 1 mantém o formato JSON do script original (migração directa do
state.json antigo). A escrita é atómica (ficheiro temporário + rename) para
um crash a meio nunca deixar o estado corrompido.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class State:
    processed_ids: dict[str, str] = field(default_factory=dict)
    failed_ids: list[str] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> State:
        if not path.exists():
            return cls()
        with path.open(encoding="utf-8") as fh:
            data = json.load(fh)
        return cls(
            processed_ids=dict(data.get("processed_ids") or {}),
            failed_ids=list(data.get("failed_ids") or []),
        )

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(
                {"processed_ids": self.processed_ids, "failed_ids": self.failed_ids},
                fh,
                indent=2,
                ensure_ascii=False,
            )
        os.replace(tmp, path)

    def mark_processed(self, entry_id: str, created_on: str) -> None:
        self.processed_ids[entry_id] = created_on
        if entry_id in self.failed_ids:
            self.failed_ids.remove(entry_id)

    def mark_failed(self, entry_id: str) -> None:
        if entry_id not in self.failed_ids:
            self.failed_ids.append(entry_id)
