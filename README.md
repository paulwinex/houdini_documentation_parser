## Houdini Documentation Parser

This script can parse Houdini Python documentation and save python script for IDE auto completion.

Doc url: http://www.sidefx.com/docs/houdini/hom/hou/

By default scrip save two files: full version (with doc strings) and mini version (no doc strings, only sourse url)

#### Usage

```
# go to some folder
python /path/to/hou_parser.py
```

#### Requires

- Python 2.7
- requests
- beautifulsoup4

Tested on documentation for houdini 16.5
