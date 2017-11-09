"""
Parse houdini documentation and create .py file for auto completion inside IDE

import hou_parser
hou_modules = hou_parser.HouModules.parse_help(verbose=True, as_text=False)
min_array = []
full_array = []
for m in sorted(hou_modules, key=lambda x: hou_parser.HouModules.ORDER.get(x.type, 0)):
    try:
        ftext = m.as_text(True)
        mtext = m.as_text(False)
        full_array.append(ftext)
        min_array.append(mtext)
    except Exception as e:
        print 'ERROR:', m.url
        print e
        continue
minify, full = '\n\n'.join(min_array), '\n\n'.join(full_array)
open('d:/hou_full.py', 'w').write(full)
open('d:/hou_min.py', 'w').write(minify)

"""
import requests, re, os
from bs4 import BeautifulSoup


class HouModules(object):
    class TYPES:
        MODULE = 'module'
        CLASS = 'class'
        METHOD = 'method'
        FUNC = 'function'
        ENUM = 'enumerate'

    ORDER = {
        TYPES.CLASS: 0,
        TYPES.MODULE: 1,
        TYPES.FUNC: 2,
        TYPES.ENUM: 3
    }

    def __init__(self, url, verbose=False, use_cache=True):
        self.is_valid = False
        self._verbose = verbose
        print '>>>', url
        self.soup = None
        self.url = url
        self.page_content = ''
        from_cache = False
        cache_file = os.path.normpath(os.path.expanduser('~/hou_help_cache/%s' % os.path.basename(url)))
        if use_cache:
            if os.path.exists(cache_file):
                self.verbose('From cache "%s"' % os.path.basename(cache_file))
                self.page_content = open(cache_file).read()
                self.soup = BeautifulSoup(self.page_content, 'html.parser')
                from_cache = True
        if not self.soup:
            self.page = requests.get(url)
            if not self.page.status_code == 200:
                self.verbose('URL not found')
                return
            self.page_content = self.page.content
            self.soup = BeautifulSoup(self.page_content, 'html.parser')

        self.type = ''
        self.name = ''
        # start parse
        self.methods = []
        self.static_functions = []
        self.inherits = []
        self.function = {}
        self.enum = []
        self.doc = ''
        self.parse_element()
        if self.is_valid and self.page_content and not from_cache:
            if not os.path.exists(os.path.dirname(cache_file)):
                os.makedirs(os.path.dirname(cache_file))
            if not os.path.exists(cache_file):
                print 'Write cache: %s' % cache_file
            cache = self.page_content
            open(cache_file, 'w').write(cache)

    def __repr__(self):
        return '<HouMod %s hou.%s>' % (self.type.upper(), self.name)

    def parse_element(self):
        title = self.soup.find('h1', {'class': 'title'}).text
        if not title:
            self.verbose('Title not found for %s' % self.url)
            return
        s = re.search(r"hou\.\s*(\w+)", title)
        if s:
            self.name = s.group(1)
            self.verbose('Name is: %s' % self.name)
        else:
            self.verbose('Name not found for %s' % self.url)
            return
        type = title.strip().split()[-1]
        if type == 'function':
            self.type = self.TYPES.FUNC
        elif type == 'class':
            self.type = self.TYPES.CLASS
        elif type == 'module':
            self.type = self.TYPES.MODULE
        summary = self.soup.find('p', {'class': 'summary'})
        if summary:
            self.doc = summary.text.strip()
        get_details = True
        if self.parse_methods() or self.parse_static_functions():
            self.verbose('Is Class')
            # self.type = self.TYPES.CLASS
        elif self.parse_enum():
            get_details = False
            self.verbose('Is Enum')
            self.type = self.TYPES.ENUM
        elif self.parse_single_function():
            self.verbose('Is Function')
            # self.type = self.TYPES.FUNC
        # else:
            # self.type = self.TYPES.MODULE
            # return
        if get_details:
            details = self.soup.find('div', {'id': 'content', 'class': None})
            elems = []
            for p in details.findChildren(recursive=False):
                if p.name == 'section':
                    break
                if p.name not in ['table', 'div']:
                    elems.append(p)

            self.doc += '\n'.join([x.text.strip() for x in elems])
        self.is_valid = True

    def parse_methods(self):
        # self methods
        ok = False
        have_methods = self.soup.find('div', {'id': 'methods-body'})
        if have_methods:
            self_methods_div = self.soup.find('div', {'class': 'methods_item_group item_group'})
            if self_methods_div:
                for m in self_methods_div.find_all('div', {'class': 'collapsible collapsed method item '}):
                    method_title = m.find('p', {'class': 'label'}).text
                    description = m.find('div', {'class': 'content'}).text
                    name, args,  ret = self.parse_method_title(method_title.strip())
                    if name:
                        self.methods.append(dict(
                            name=name,
                            args=self.parse_args(args),
                            ret=ret,
                            doc=self.legal_text(description).strip()
                        ))
                    else:
                        print 'Error parse "%s"' % method_title
            ok = True

        # inherits
        inherit = self.soup.find('div', {'id': re.compile(r'methods-from.*')})
        if inherit:
            inherit = self.soup.find_all('h2', {'id': re.compile(r'methods-from.*')})
            for inh in inherit:
                self.inherits.append(inh.text.split('from')[-1].strip().split('hou.')[-1])
            ok = True
        return ok

    def parse_static_functions(self):
        ok = False
        functions = self.soup.find('div', {'id': 'functions-body'})
        if functions:
            for f in functions.find_all('div', {'class': 'collapsible collapsed method item '}):
                name, args, ret = self.parse_method_title(f['data-title'])
                if not name:
                    return None, None, None
                description = f.find('div', {'class': 'content'}).text
                self.static_functions.append(dict(
                    name=name,
                    args=self.parse_args(args),
                    ret=ret,
                    doc=self.legal_text(description).strip()
                ))
            ok = True
        return ok

    def parse_single_function(self):
        usage = self.soup.find('div', {'class': 'usage_group'})
        if usage:
            title = usage.find('p', {'class': 'label'}).text.strip()
            doc = [p.text for p in self.soup.find('div', {'id': 'content'}).find_all('p', {'class': None})]
            name, args, ret = self.parse_method_title(title)
            if name:
                self.function = dict(
                    name=name,
                    args=self.parse_args(args),
                    ret=ret,
                    doc=self.legal_text('\n'.join(doc)).strip()
                )
                self.name = name
                # self.doc = doc
            else:
                print 'Error get name', title
            return True
        else:
            content = self.soup.find('div', {'class': 'title-content '})
            if content:
                # title = content.find('h1', {'class': 'title'}).text.strip()
                summary = content.find('p', {'class': 'summary'})
                if summary:
                    summary = summary.text.strip()
                else:
                    summary = ''
                pp = (self.soup.find('div', {'id': 'content'}).find('usage')
                      or self.soup.find('div', {'class': 'usage item'})
                      or self.soup.find('div', {'id': 'content'})).find_all('p')
                pp = [p.text.strip() for p in pp if p.text.strip()]
                usage = pp.pop(0)
                name, args, ret = self.parse_method_title(usage)
                docs = '\n'.join(pp + [x.text for x in self.soup.find('div', {'id': 'content'}).find_all('pre')])
                docs = summary + '\n\n' + docs
                self.function = dict(
                    name=name,
                    args=self.parse_args(args),
                    ret=ret,
                    doc=self.legal_text(docs).strip()
                )
                self.doc = docs
            self.doc = ''

        return False

    def parse_enum(self):
        ok = False
        values = self.soup.find('div', {'id': 'values-body'})
        if values:
            # http://www.sidefx.com/docs/houdini/hom/hou/saveMode
            # enumerate
            items = values.find_all('div', {'class': 'values_item item def'})
            if items:
                ok = True
                for el in items:
                    name = el.find('p', {'class': 'label'}).text.strip().strip('.')
                    description = el.find('div', {'class': 'content'})
                    if description:
                        description = description.text.replace('\n\n', '\n')
                    self.enum.append(dict(
                        name=name,
                        description=description.strip()
                    ))
            else:
                items = values.find_all('li')
                if items:
                    ok = True
                    for li in items:
                        pp = li.find_all('p')
                        if pp:
                            name = pp.pop(0)
                            name = name.text.strip().split('.')[-1]
                            if pp:
                                description = pp[0].text
                            else:
                                description = ''
                            self.enum.append(dict(
                                name=name,
                                description=description.strip()
                            ))
                        else:
                            print 'Wrong Enum parsing'
        summary = self.soup.find('p', {'class': 'summary'})
        if summary:
            self. doc = summary.text
        docs = self.soup.find('div', {'id': 'content'})
        if docs:
            doc = '\n'.join([x.text for x in docs.find_all('p', {'class': None}, recursive=False)])
            self.doc = self.doc + '\n' + doc
        return ok

    @classmethod
    def parse_method_title(cls, title):
        title = re.sub(r'[^\x00-\x7F]', '==', title)
        title = re.sub(r'->', '==', title)
        title = cls.legal_text(title).replace('\n', ' ').strip()
        name, args, ret = None, None, None
        if '==' in title:
            deff, ret = title.split('==')
        else:
            deff, ret = title, ''
        # m = re.match(r"(\w+)(\(.*?\))[\s=]*([\w\s.]*)$", title)
        # m = re.search(r"(\w+)(\(.*\))[\s=]*?(.*)", title)
        m = re.search(r"(\w+)(\(.*\))", deff)
        if m:
            name, args = [x.strip().strip(':') for x in m.groups()]
        return name, args, ret

    @classmethod
    def parse_return(cls, line):
        line = line.replace('=', '').strip()
        # int , float , str or tuple
        if re.match(r"(.+,)+\s*\w+\s*or\s*\w+", line):
            return 'object'
        # single class
        m = re.match(r"^hou.(\w+)$", line)
        if m:
            return m.group(1)
        # class or none
        m = re.match(r"([\w.]+)\s+or\s+(None|none)", line)
        if m:
            return cls.type_to_data(m.group(1))
        # tuple of enums
        m = re.match(r"tuple\s*of\s*([\w._]+)\s+enum\s+values", line)
        if m:
            return '(EnumValue, )'
        # tuple of []
        m = re.match(r"tuple\s*of\s*\[Hom:([\w._]+)\]", line)
        if m:
            return '(%s, )' % cls.type_to_data(m.group(1))
        # tuple of
        m = re.match(r"tuple\s*of\s*([\w._]+)", line)
        if m:
            return '(%s, )' % cls.type_to_data(m.group(1))
        # tuple ot tuples
        m = re.match(r"\(\s*tuple\s+of\s+([\w._]+)\s*,\s+tuple\s+of\s+tuples\s+of\s+([\w._]+).*", line)
        if m:
            return '(%s, ((%s,),))' % (cls.type_to_data(m.group(1)), cls.type_to_data(m.group(2)))
        # tuple ot tuples 2
        m = re.search(r"tuple\s+of\s+\(([\w\s.,_]+)+\)", line)
        if m:
            vals = [cls.type_to_data(x.strip()) for x in m.group(1).split(',')]
            return '((%s,),)' % ', '.join(vals)
        # hou.primType enum value
        m = re.match(r"([\[\]:\w.]+)\s+enum\s+value", line)
        if m:
            return 'EnumValue'  # type_to_data(m.group(1))
        m = re.match(r"dict\s+of\s+([\w.]+)\s+to\s+([\w.]+)", line)
        if m:
            return '{%s: %s}' % (cls.type_to_data(m.group(1)), cls.type_to_data(m.group(2)))
        m = re.match(r"dict\s+of\s+[\s\w\[\].:]+\s+enum\s+value\s+to\s+([\w.]+)", line)
        if m:
            return '{EnumValue: %s}' % cls.type_to_data(m.group(1))

        m = re.match(r"\(([\s\w,._]+)\)", line)
        if m and ',' in line:
            args = [cls.type_to_data(x.strip()) for x in m.group(1).split(',')]
            return '(%s,)' % ', '.join(args)
        m = re.match(r"dictionary\s+of\s+\((([\w\/.]+)\s?\,\s?tuple\s+of\s+([\w.]+))\)\s+pairs", line)
        if m:
            k, v = m.group(2).split('/')[-1], m.group(3)
            return '{%s: (%s, )}' % (cls.type_to_data(k), cls.type_to_data(v))
        m = re.match(r".*(Q[\w]+)\s+subclass", line)
        if m:
            # need to import QWidget to script
            return m.group(1)
        m = re.match(r"\(([\w.+]+)\s*,\s*tuple\s+of\s+([\w._]+)\)", line)
        if m:
            k, v = m.groups()
            return '(%s, (%s,))' % (cls.type_to_data(k), cls.type_to_data(v))
        m = re.match(r"\(([\w.+]+)\s*,\s*tuple\s+of\s+([\w._]+)\s+and\s+([\w._]+)\s+tuples\)", line)
        if m:
            v1, v2, v3 = m.groups()
            return '(%s, (%s (%s,),))' % (cls.type_to_data(v1), cls.type_to_data(v2), cls.type_to_data(v3))
        variants = [x.strip().strip(',') for x in re.findall(r"([\w.]+\s*,?\s*)", line)]
        if 'or' in variants:
            return 'object'
        return cls.type_to_data(line)

    @classmethod
    def parse_args(cls, args):
        nargs = []
        args = args.strip()
        if args[0] == '(':
            args = args[1:]
        if args[-1] == ')':
            args = args[:-1]
        if not args.strip():
            return nargs
        s = re.search(r"=\s*(hou.([\w+]+)\(\(.*?\)\))", args)
        if s:
            args = args.replace(s.group(1), s.group(2))
        for a in args.split(','):
            a = a.strip().replace('Hom:hou.', '').replace('hou.', '').replace('Hom.', '').replace('Hom:', '')
            if '=' in a:
                name, val = a.split('=')
                name = name.strip()
                val = val.strip()
                if ' ' in name:
                    name = name.split(' ')[-1]
                nargs.append('%s=%s' % (name.strip(), cls.type_to_data(val)))
                continue
            if '[' in a or ']' in a:
                a = a.replace('[', '').replace(']', '').replace('::', ".").replace(':', ".").split('hou.')[-1]
                nargs.append(a)
                continue
            if ' ' in a:
                a = a.split()[-1]
            nargs.append(a)
        return nargs

    @classmethod
    def type_to_data(cls, line):
        line = line.replace('=', '').replace('::', '.').replace(':', '.').strip()
        if not line:
            return 'None'
        if line in ['double', 'float']:
            return '0.0'
        elif line in ['int', 'start', 'end']:
            return '0'
        elif line == 'bool':
            return 'True'
        elif line in ['string', 'str', 'strings']:
            return '""'
        elif line in ['dict', '{}']:
            return '{}'
        elif line == 'parm':
            return 'Parm'
        elif line == '()':
            return 'tuple()'
        elif line.startswith('hou.') or 'hou.' in line:
            return line.split('hou.')[-1]
        elif line.startswith('Hom.') or 'Hom.' in line:
            return line.split('hou.')[-1]

        elif line[0].istitle():
            return line
        else:
            return line

    def verbose(self, *args):
        if self._verbose:
            print ' '.join([str(x) for x in args])

    @classmethod
    def legal_text(cls, text):
        text = re.sub(r'[^\x00-\x7F]', ' ', text)
        text = re.sub(r"(\n)+", r"\n", text).strip()
        return text

    @classmethod
    def add_self_to_args(cls, args, s='self'):
        args = [a.strip() for a in args if a.strip() != s]
        args.insert(0, s)
        return args

    @classmethod
    def args_to_str(cls, args, add_self=None):
        if add_self is not None:
            args = cls.add_self_to_args(args, str(add_self))
        return '(%s)' % ', '.join(args)

    def as_text(self, docs=True):
        text = ''
        #################### CLASS
        if self.type == self.TYPES.CLASS:
            if docs:
                d = """\"\"\"
    {url}
    {doc}
    \"\"\"""".format(doc=self.legal_text(self.doc).replace('"""', "'''") if docs else '',
                     url=self.url)
            else:
                d = """\"\"\"
    {url}
    \"\"\"""".format(url=self.url)
            text += """
class {name}({inherit}):
    {doc}
""".format(
                name=self.name,
                inherit=', '.join([x.split('.')[-1] for x in self.inherits]),
                doc=d
            )
            for m in self.methods:
                if docs:
                    d = """\"\"\"
        {doc}
        # return {ret}
        \"\"\"\n        """.format(doc='\n        '.join(self.legal_text(m['doc'].replace('"""', "'''")).strip().split('\n')) if docs else '',
                                   ret=m['ret'].replace('=', '').strip())
                else:
                    d = ''

                text += """
    def {name}{args}:
        {doc}return {parse_ret}
""".format(
                    name=m['name'],
                    args=self.args_to_str(m['args'], 'self'),
                    doc=d,
                    parse_ret=self.parse_return(m['ret'])
                )
            for f in self.static_functions:
                if docs:
                    d = """\"\"\"
        {doc}
        # return {ret}
        \"\"\"\n        """.format(doc='\n        '.join(self.legal_text(f['doc'].replace('"""', "'''")).strip().split('\n')) if docs else '',
                                   ret=f['ret'].replace('=', '').strip())
                else:
                    d = ''
                text += """
    @classmethod
    def {name}{args}:
        {doc}return {parse_ret}
""".format(
                    name=f['name'],
                    # args=self.add_self_to_args(f['args'], 'cls'),
                    args=self.args_to_str(f['args'], 'cls'),
                    doc=d,
                    parse_ret=self.parse_return(f['ret'])
                )
        ##################### MODULE
        elif self.type == self.TYPES.MODULE:
            if docs:
                d ="""\"\"\"
    {url}
    {doc}
    \"\"\"""".format(doc='\n    '.join(self.legal_text(self.doc.replace('"""', "'''")).strip().split('\n')),
                     url=self.url)
            else:
                d = """\"\"\"
    {url}
    \"\"\"""".format(url=self.url)
            text += """
class {name}({inherit}):
    {doc}
""".format(
                name=self.name,
                # url=self.url,
                inherit=', '.join([x.split('.')[0] for x in self.inherits]),
                doc=d
            )
        ########################### FUNCTION
        elif self.type == self.TYPES.FUNC:
            if isinstance(self.doc, list):
                self.doc = '\n    '.join(self.doc)
            if docs:
                d = """
    \"\"\"
    {url}
    {doc}
    \"\"\"
    # return {ret}\n    """.format(
                    doc=self.legal_text(self.doc) + '\n\n    '+'\n    '.join(self.legal_text(self.function['doc'].replace('"""', "'''")).strip().split('\n')),
                    url=self.url,
                    ret=self.function['ret'].replace('=', '').strip())
            else:
                d = ''
            text += """
def {name}{args}:
    {doc}return {parse_ret}
""".format(
                name=self.function['name'],
                url=self.url,
                args=self.args_to_str(self.function['args']),
                doc=d,
                parse_ret=self.parse_return(self.function['ret'])
            )
        ########################## ENUM
        elif self.type == self.TYPES.ENUM:
            d = ''
            if docs:
                d = """
    {doc}
""".format(doc=self.doc.replace('\n', '    \n'))
            text += """
class {name}:
    \"\"\"
    {url}
    {doc}
    \"\"\"
{enum}
""".format(
                name=self.name,
                doc=d,
                url=self.url,
                enum='\n'.join(['    {name}=EnumValue'.format(name=x['name']) +
                                ('\n    # {doc}'.format(doc=self.legal_text(x['description'].replace('\n', '\n    # ').replace('"""', "'''")).strip())
                                 if (x['description'].strip() and docs)else '') for x in self.enum])
            )
        return text

    @staticmethod
    def sort_classes(classes):
        next = True
        i = 0
        while next and i < 1000:
            i += 1
            for curr_cls in classes:
                for cls in classes:
                    if cls.name == curr_cls.name:
                        continue
                    if curr_cls.name in cls.inherits:
                        if classes.index(curr_cls) > classes.index(cls):
                            cur = classes.pop(classes.index(curr_cls))
                            print 'Move', cur
                            classes.insert(classes.index(cls) - 1, cur)
                            break
                    next = False
            else:
                next = False
        return classes

    @classmethod
    def parse_help(cls, verbose=False, as_text=True, save_cache=True):
        root_url = 'http://www.sidefx.com/docs/houdini/hom/hou/'
        page = requests.get(root_url)
        s = BeautifulSoup(page.content, 'html.parser')
        hou_modules = []
        all_modules = s.find_all('li', {'class': 'subtopics_item'})
        import random
        random.shuffle(all_modules)
        for i, elem in enumerate(all_modules):
            if verbose:
                print '-'*50
                print '%s/%s: %s' % ('{:>{}}'.format(i, len(str(len(all_modules)))), len(all_modules), elem['data-title'])
            hou_mod = cls(root_url + elem.find('a')['href'], verbose, save_cache)
            if hou_mod.is_valid:
                hou_modules.append(hou_mod)
        # sort
        classes = [x for x in hou_modules if x.type == HouModules.TYPES.CLASS]
        modules = [x for x in hou_modules if x.type == HouModules.TYPES.MODULE]
        functions = [x for x in hou_modules if x.type == HouModules.TYPES.FUNC]
        enumerates = [x for x in hou_modules if x.type == HouModules.TYPES.ENUM]
        classes = HouModules.sort_classes(classes)
        modules = sorted(modules, key=lambda x: x.name)
        functions = sorted(functions, key=lambda x: x.name)
        enumerates = sorted(enumerates, key=lambda x: x.name)
        hou_modules = enumerates + classes + modules + functions

        if not as_text:
            return hou_modules
        # to text
        min_array = []
        full_array = []
        for m in hou_modules:
            try:
                ftext = m.as_text(True)
                mtext = m.as_text(False)
                full_array.append(ftext)
                min_array.append(mtext)
            except Exception as e:
                print 'ERROR:', m.url
                print e
                continue
        qt_import = 'from PySide2.QtWidgets import *\n'
        return qt_import+'\n\n'.join(min_array), qt_import+'\n\n'.join(full_array)


if __name__ == '__main__':
    minify, full = HouModules.parse_help(verbose=True, as_text=True)
    print 'WRITE'
    open('hou_full.py', 'w').write(full)
    print 'FULL  SAVED: d:/hou_full.py'
    open('hou_min.py', 'w').write(minify)
    print 'SHORT SAVED: d:/hou_min.py'
    print 'COMPLETE'

