#!/bin/bash
export CC=/usr/bin/gcc-12
export CXX=/usr/bin/g++-12

# 合成用
CUDA_VISIBLE_DEVICES=0,1,2,3 vllm serve /data/models/Qwen3-32B \
    --tensor-parallel-size 4 \
    --port 8000 \
    --gpu-memory-utilization 0.8 \
    --max_model_len 8192 \
    --max-num-seqs 4 \
    --dtype auto \
    --trust-remote-code \
    --reasoning-parser qwen3 > logs/qwen3_32b.log 2>&1 &
echo "Qwen3-32B started in background. Logs: logs/qwen3_32b.log"

# 等待几秒钟确保第一个服务启动
sleep 5

# 第一批模型
CUDA_VISIBLE_DEVICES=0 vllm serve /data/models/Qwen2.5-3B-Instruct \
--tensor-parallel-size 1 \
--port 8002 \
--gpu-memory-utilization 0.9 \
--max_model_len 15000 \
--max-num-seqs 1 \
--dtype auto \
--trust-remote-code > logs/qwen2_5_3b.log 2>&1 &
echo "Qwen2.5-3B-Instruct started in background. Logs: logs/qwen2_5_3b.log"

# 后台运行 Llama-3.2-3B-Instruct 模型
echo "Starting Llama-3.2-3B-Instruct model on port 8001..."
CUDA_VISIBLE_DEVICES=1 nohup vllm serve /data/models/Llama-3.2-3B-Instruct \
--tensor-parallel-size 1 \
--port 8001 \
--gpu-memory-utilization 0.9 \
--max_model_len 15000 \
--max-num-seqs 1 \
--dtype auto \
--trust-remote-code > logs/llama_3_2_3b.log 2>&1 &
echo "Llama-3.2-3B-Instruct started in background. Logs: logs/llama_3_2_3b.log"

CUDA_VISIBLE_DEVICES=2,3 vllm serve /data/models/Meta-Llama-3.1-8B-Instruct \
--tensor-parallel-size 2 \
--port 8003 \
--gpu-memory-utilization 0.9 \
--max_model_len 15000 \
--max-num-seqs 2 \
--dtype auto \
--trust-remote-code > logs/llama_3_1_8b.log 2>&1 &
echo "Meta-Llama-3.1-8B-Instruct started in background. Logs: logs/llama_3_1_8b.log"

# 第二批模型
CUDA_VISIBLE_DEVICES=0,1 vllm serve /data/models/Qwen2.5-7B-Instruct \
--tensor-parallel-size 2 \
--port 8004 \
--gpu-memory-utilization 0.9 \
--max_model_len 15000 \
--max-num-seqs 2 \
--dtype auto \
--trust-remote-code > logs/qwen2_5_7b.log 2>&1 &
echo "Qwen2.5-7B-Instruct started in background. Logs: logs/qwen2_5_7b.log"

CUDA_VISIBLE_DEVICES=2,3 vllm serve /data/models/Mistral-7B-Instruct-v0.3 \
--tensor-parallel-size 2 \
--port 8005 \
--gpu-memory-utilization 0.9 \
--max_model_len 15000 \
--max-num-seqs 2 \
--dtype auto \
--trust-remote-code > logs/mistral_7b.log 2>&1 &
echo "Mistral-7B-Instruct started in background. Logs: logs/mistral_7b.log"

echo "All models started in background. Check logs directory for output."
echo "To stop the services, use 'ps aux | grep vllm' to find the PIDs and 'kill <PID>' to stop them."
