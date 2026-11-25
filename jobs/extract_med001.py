import sys, fsspec, pyarrow.parquet as pq, pyarrow as pa
base = "https://huggingface.co/datasets/DiscoPosse/lmcache-agentic-traces/resolve/main/data/"
tabs = []
for i in range(5):
    url = base + f"train-0000{i}-of-00005.parquet"
    with fsspec.open(url, "rb", block_size=4*1024*1024) as f:
        t = pq.ParquetFile(f).read(columns=["session_id", "model", "pre_gap", "output_length"])
        tabs.append(t); print(i, t.num_rows, flush=True)
pq.write_table(pa.concat_tables(tabs), sys.argv[1])
