# Updating Illustrations

The **cloudigrade** docs include some sequence diagrams that you may want to update periodically. Because `seqdiag` pulls in a lot of heavy dependencies, we do not include it anywhere in our `pyproject.toml` for `poetry`. If you want to rebuild the diagrams, try commands similar to the following:

```bash
pip install seqdiag

cd docs/illustrations

for FILE in *.diag
do
  seqdiag -Tsvg $FILE
done
```
