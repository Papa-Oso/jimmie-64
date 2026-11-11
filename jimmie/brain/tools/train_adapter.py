"""Starter for the "can he improvise with transcript search off?" experiment: a small LoRA on
context -> his actual next turn.

NOT RUN by its author. It is a plain Hugging Face PEFT loop with nothing project-specific in it;
check it against the installed transformers/peft versions before trusting it, and do the
one-step memory check first (--max-steps 1) exactly as the project plan already requires.

Input: rows from `python -m jimmie_brain export turns.jsonl train.jsonl` (speaker-verified, training
streams only). The prompt shape matches jimmie_brain.writer with retrieval off, so the adapter is
tested in the same form it was trained in.

Recommended base: a 4B-class instruct model rather than the 12B. The 12B already peaks near
10.7 GB of the 12 GB card with nothing else loaded, which leaves no room for the voice model;
a 4B model plus adapter plus Qwen3-TTS fits, and style is what the adapter has to carry.

  python train_adapter.py --base <hf model dir> --train train.jsonl --dev dev.jsonl --out adapter-r1 --max-steps 1
"""
import argparse
import json
from pathlib import Path

SYSTEM = "You write what Jimmie says out loud. Reply with one spoken line, nothing else."


def rows(path):
    with Path(path).open(encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            context = r["context"].strip() or "(he has not said anything for a while)"
            yield [{"role": "system", "content": SYSTEM},
                   {"role": "user", "content": f"He was just saying: {context}\nWhat does he say next?"},
                   {"role": "assistant", "content": r["response"]}]


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--base", required=True); p.add_argument("--train", required=True); p.add_argument("--dev")
    p.add_argument("--out", required=True); p.add_argument("--max-steps", type=int, default=600)
    p.add_argument("--rank", type=int, default=16); p.add_argument("--lr", type=float, default=1e-4)
    p.add_argument("--max-length", type=int, default=192); p.add_argument("--batch", type=int, default=8)
    a = p.parse_args()

    import torch
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    tok = AutoTokenizer.from_pretrained(a.base)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(a.base, device_map="auto", quantization_config=BitsAndBytesConfig(
        load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_compute_dtype=torch.bfloat16))
    model = get_peft_model(prepare_model_for_kbit_training(model), LoraConfig(
        r=a.rank, lora_alpha=2 * a.rank, lora_dropout=0.05, task_type="CAUSAL_LM", target_modules="all-linear"))

    def encode(messages):
        # Some chat templates reject a system role; fold it into the user turn if so.
        try:
            prompt = tok.apply_chat_template(messages[:-1], tokenize=False, add_generation_prompt=True)
        except Exception:
            merged = [{"role": "user", "content": messages[0]["content"] + "\n\n" + messages[1]["content"]}]
            prompt = tok.apply_chat_template(merged, tokenize=False, add_generation_prompt=True)
        head = tok(prompt, add_special_tokens=False)["input_ids"]
        tail = tok(messages[-1]["content"] + tok.eos_token, add_special_tokens=False)["input_ids"]
        ids = (head + tail)[-a.max_length:]
        labels = ([-100] * len(head) + tail)[-a.max_length:]      # learn only his reply
        return ids, labels

    def batches(path):
        data = [encode(m) for m in rows(path)]
        generator = torch.Generator().manual_seed(0)
        while True:
            order = torch.randperm(len(data), generator=generator).tolist()
            for i in range(0, len(order) - a.batch + 1, a.batch):
                chunk = [data[j] for j in order[i:i + a.batch]]
                width = max(len(ids) for ids, _ in chunk)
                ids = torch.tensor([[tok.pad_token_id] * (width - len(x)) + x for x, _ in chunk])
                labels = torch.tensor([[-100] * (width - len(y)) + y for _, y in chunk])
                yield ids, labels, (ids != tok.pad_token_id).long()

    optimizer = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=a.lr)
    model.train()
    for step, (ids, labels, mask) in enumerate(batches(a.train), 1):
        loss = model(input_ids=ids.to(model.device), attention_mask=mask.to(model.device), labels=labels.to(model.device)).loss
        loss.backward()
        optimizer.step()
        optimizer.zero_grad()
        if step == 1 or step % 25 == 0:
            peak = torch.cuda.max_memory_allocated() / 2 ** 30 if torch.cuda.is_available() else 0
            print(f"step {step} loss {loss.item():.3f} peak {peak:.1f} GiB", flush=True)
        if step >= a.max_steps:
            break
    model.save_pretrained(a.out)
    tok.save_pretrained(a.out)
    print("saved", a.out, "- convert for llama.cpp with its convert_lora_to_gguf.py, then serve with --lora")


if __name__ == "__main__":
    main()
