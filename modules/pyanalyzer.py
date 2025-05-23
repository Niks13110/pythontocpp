import ast
from modules import pycatalystexceptions as pcex
from modules import portedfunctions as pf

class PyAnalyzer():
    """
    This is the main class of PyCatalyst that performs the actual analysis and 
    translates python calls to C++ calls
    """
    # Helps evaluate variable types when performing operations on different
    # types (lower value higher precedence)
    type_precedence_dict = {"str": 0, "float": 1, "int": 2, "bool": 3,
                            "auto": 8, "None": 9, "void": 9}
    # Python operators translated to C++ operators
    operator_map = {"Add": "+", "Sub": "-", "Mult": " * ", "Div": "/",
                    "Mod": " % ", "LShift": " << ", "RShift": " >> ",
                    "BitOr": " | ", "BitAnd": " & ", "BitXor": " ^ ",
                    "FloorDiv": "/", "Pow": "Pow", "Not": "!",
                    "Invert": "~", "UAdd": "+", "USub": "-", "And": " && ",
                    "Or": " || "
                    }
    # Tuple of all functions we have a special conversion from python to C++
    ported_functions = ("print", "sqrt")
    
    
    # Python Comparison operators translated to C++ operators
    # We aren't able to do in/is checks easily, so they are excluded from the
    # mapping
    comparison_map = {"Eq": " == ", "NotEq": " != ", "Lt": " < ",
                      "LtE": " <= ", "Gt": " > ", "GtE": " >= "
                      }
    
    def __init__(self, output_files, raw_lines):
        """
        Initializes an object that will recurse through an AST to convert
        python code text to objects representing C++ code

        Parameters
        ----------
        output_files : list of CPPFile objects
            List to store CPPFiles that the analyzer will reference during
            analysis
        raw_lines : list of str
            List containing the original python script, line by line
        """
        self.output_files = output_files

        self.raw_lines = raw_lines
        
    def analyze(self, tree, file_index, function_key, indent):
        """
        This launches the analysis process, starting with pre-analysis before
        beginning the main analysis step

        Parameters
        ----------
        tree : List of ast nodes
            List containing ast nodes from ast.parse
        file_index : int
            Index of the file to write to in the output_files list
        function_key : str
            Key used to find the correct function in the function dictionary
        indent : int
            How much indentation a line should have
        """
        self.pre_analysis(tree, file_index, indent)
        self.analyze_tree(tree, file_index, function_key, indent)
        
        
    def pre_analysis(self, tree, file_index, indent):
        """
        Performs pre-analysis on the script by going through and translating
        all functions that have been declared in this script

        Parameters
        ----------
        tree : List of ast nodes
            List containing ast nodes from ast.parse
        file_index : int
            Index of the file to write to in the output_files list
        indent : int
            How much indentation a line should have
        """
        # First work through function declarations so we know what calls go to
        # self written functions
        for node in tree:
            if node.__class__ is ast.FunctionDef:
                self.parse_function_header(node,file_index)
        
        # Now we'll parse the bodies of the functions
        for node in tree:
            if node.__class__ is ast.FunctionDef:
                self.analyze_tree(node.body, file_index, node.name, indent)
                
    def parse_function_header(self,node,file_index):
        """
        Parses an ast.FunctionDef node and determines the function name and
        parameters and stores this information in a CPPFunction object which
        is stored in the corresponding CPPFile object

        Parameters
        ----------
        node : ast.FunctionDef
            Node containing the function to parse a header from
        file_index : int
            Index of the file to write to in the output_files list
        """
        func_ref = self.output_files[file_index].functions
        args = node.args
        
        # Verify the function can actually be converted to C++
        if len(args.kw_defaults) > 0 or len(args.kwonlyargs) > 0 \
            or len(args.posonlyargs) > 0 or args.kwarg is not None \
                or args.vararg is not None:
            return
        
        # Default values not directly linked, but they are in order, so we
        # figure out the index offset of when we should begin applying default
        # values to parameters
        default_args_index = len(args.args) - len(args.defaults)
        params = {}
        
        for index in range(len(args.args)):
            name = args.args[index].arg

            # Once index has reached the offset index, we need to start
            # applying default values
            if index >= default_args_index:
                default = args.defaults[index-default_args_index]
                default_type = [type(default.value).__name__]

                # Special handler for strings since their value needs to be
                # wrapped in quotes
                if default_type[0] == "str":
                    params[name] = cvar.CPPVariable(name + "=\"" + default.value + "\"",
                                                    -1, default_type)
                else:
                    params[name] = cvar.CPPVariable(name + "=" + str(default.value),
                                                    -1, default_type)
            else:
                params[name] = cvar.CPPVariable(name, -1, ["auto"])

        func_ref[node.name] = cfun.CPPFunction(node.name, node.lineno,
                                               node.end_lineno, params)
    
    
    def analyze_tree(self, tree, file_index, function_key, indent):
        """
        Accepts an AST node body list and parses through it
        recursively. It will look at each node and call
        the respective functions to handle each type

        Parameters
        ----------
        tree : List of ast nodes
            List containing ast nodes from ast.parse
        file_index : int
            Index of the file to write to in the output_files list
        function_key : str
            Key used to find the correct function in the function dictionary
        indent : int
            How much indentation a line should have
        """
        for node in tree:
            # Skipping function definitions as we handled them during
            # pre-analysis
            if node.__class__ is not ast.FunctionDef:
                # Using strategy found in ast.py built-in module
                handler_name = "parse_" + node.__class__.__name__
                # Will find if the function called handler_name exists,
                # otherwise it returns parse_unhandled(fallback function)
                handler = getattr(self, handler_name, self.parse_unhandled)
                handler(node, file_index, function_key, indent)
    
    
    def parse_unhandled(self, node, file_index, function_key, indent,
                        reason="TODO: Code not directly translatable, manual port required"):
        """
        Handler for any code that cannot be properly translated.
        This will bring the code verbatim from the original python
        script and wrap it in a C++ comment and add the reason it
        wasn't translated one line above it

        Parameters
        ----------
        node : ast node
            The ast node that couldn't be translated
        file_index : int
            Index of the file to write to in the output_files list
        function_key : str
            Key used to find the correct function in the function dictionary
        indent : int
            How much indentation a line should have
        reason : str
            The reason why a line of code wasn't translated
        """
        # Get a reference to the correct function to shorten code width
        func_ref = self.output_files[file_index].functions[function_key]
        func_ref.lines[node.lineno] = cline.CPPCodeLine(node.lineno,
                                                        node.lineno,
                                                        node.end_col_offset,
                                                        indent,
                                                        "/*" + self.raw_lines[node.lineno-1],
                                                        "", reason)

        # If the code spanned multiple lines, we need to pull all
        # of the lines from the original script, not just the first
        # line
        for index in range(node.lineno+1, node.end_lineno+1):
            func_ref.lines[index] = cline.CPPCodeLine(index,
                                                      index,
                                                      node.end_col_offset,
                                                      indent,
                                                      self.raw_lines[index-1])
        # Add the closing comment symbol on the last line
        func_ref.lines[node.end_lineno].code_str += "*/"

    # Imports
    def parse_Import(self, node, file_index, function_key, indent):
        """
        Handles parsing an ast.Import node. We don't translate this
        so we just pass on calls to it

        Parameters
        ----------
        node : ast.Import
            The ast.Import node to be translated
        file_index : int
            Index of the file to write to in the output_files list
        function_key : str
            Key used to find the correct function in the function dictionary
        indent : int
            How much indentation a line should have
        """
        pass

    def parse_ImportFrom(self, node, file_index, function_key, indent):
        """
        Handles parsing an ast.ImportFrom node. We don't translate this
        so we just pass on calls to it

        Parameters
        ----------
        node : ast.ImportFrom
            The ast.ImportFrom node to be translated
        file_index : int
            Index of the file to write to in the output_files list
        function_key : str
            Key used to find the correct function in the function dictionary
        indent : int
            How much indentation a line should have
        """
        pass          
    
    # Definitions
    def parse_ClassDef(self, node, file_index, function_key, indent):
        """
        Handles parsing an ast.ClassDef node. We don't translate this
        so we just pass on calls to it

        Parameters
        ----------
        node : ast.ClassDef
            The ast.ClassDef node to be translated
        file_index : int
            Index of the file to write to in the output_files list
        function_key : str
            Key used to find the correct function in the function dictionary
        indent : int
            How much indentation a line should have
        """
        pass
    
    # Control Statements
    def parse_If(self, node, file_index, function_key, indent, if_str="if"):
        """
        Handles parsing an ast.If node. Can be called recursively to handle
        nested ifs.

        Parameters
        ----------
        node : ast.If
            The ast.If node to be translated
        file_index : int
            Index of the file to write to in the output_files list
        function_key : str
            Key used to find the correct function in the function dictionary
        indent : int
            How much indentation a line should have
        if_str : str
            Indicates whether to be an if or else if statement
        """
        func_ref= self.output_files[file_index].functions[function_key]
        
        # Parse conditions and add in the code to the current function
        
        try:
            test_str= self.recurse_operator(node.test,file_index,function_key)[0]
            
        except pcex.TranslationNotSupported as ex:
            self.parse_unhandled(node, file_index,function_key,indent, ex.reason)
            return
        
        func_ref.lines[node.lineno]= cline.CPPCodeLine(node.lineno, 
                                                      node.end_lineno, 
                                                      node.end_col_offset,
                                                      indent,
                                                      if_str+" ("+ test_str + ")\n"
                                                      + indent*cline.CPPCodeLine.tab_delimiter
                                                      +"{")
        self.analyze_tree(node.body,file_index, function_key,indent+1)
        
        # Get the last code line and add the closing bracket
        func_ref.lines[node.body[-1].end_lineno].code_str+="\n" + indent*cline.CPPCodeLine.tab_delimiter+ "}"
        
        # Looking for else if or else cases
        if len(node.orelse) == 1 and node.orelse[0].__class__ is ast.If:
            # Else if case
            self.parse_If(node.orelse[0], file_index, function_key, indent,
                          "else if")
        elif len(node.orelse)> 0:
            #Else case
            else_lineno,else_end_col_offset= self.find_else_lineno(node.orelse[0].lineno-2)
            func_ref.lines[else_lineno]= cline.CPPCodeLine(else_lineno,
                                                           else_lineno,
                                                           else_end_col_offset,
                                                           indent,
                                                           "else\n"+ indent*cline.CPPCodeLine.tab_delimiter + "{")
            self.analyze_tree(node.orelse, file_index, function_key, indent+1)
            
            # Get the last code line and add the closing bracket
            func_ref.lines[node.orelse[-1].end_lineno].code_str+= "\n" + indent*cline.CPPCodeLine.tab_delimiter + "}"
    
    
    def find_else_lineno(self, search_index):
        """
        Finds the first else statement starting from the search_index and
        searching upwards in the original python code

        Parameters
        ----------
        search_index : int
            The line number to start searching for the else statement

        Returns
        -------
        search_index : int
            Line number of the else statement
        end_col_offset : int
            Index of the last character of the else in the original python code

        Raises
        ------
        TranslationNotSupported
            If an else is not found
        """        
        while search_index > -1:
            # Check line isn't a comment
            if self.raw_lines[search_index].lstrip()[0] == "#":
                search_index -= 1
                continue
            else:
                end_col_offset = self.raw_lines[search_index].find("else:")
                if end_col_offset < 0:
                    raise pcex.TranslationNotSupported("TODO: No corresponding else found")
                else:
                    end_col_offset += 4
                    
                search_index += 1
                return search_index, end_col_offset

    def parse_While(self, node, file_index, function_key, indent):
        """
        Handles parsing an ast.While node. Can be called recursively to handle
        nested whiles.

        Parameters
        ----------
        node : ast.While
            The ast.While node to be translated
        file_index : int
            Index of the file to write to in the output_files list
        function_key : str
            Key used to find the correct function in the function dictionary
        indent : int
            How much indentation a line should have
        """
        func_ref = self.output_files[file_index].functions[function_key]
        
        try:
            test_str = self.recurse_operator(node.test, file_index, function_key)[0]
        except pcex.TranslationNotSupported as ex:
            self.parse_unhandled(node, file_index, function_key, indent, ex.reason)
            return
        
        func_ref.lines[node.lineno] = cline.CPPCodeLine(node.lineno,
                                                        node.end_lineno,
                                                        node.end_col_offset,
                                                        indent,
                                                        "while (" + test_str + ")\n"
                                                        + indent * cline.CPPCodeLine.tab_delimiter
                                                        + "{")
        
        self.analyze_tree(node.body, file_index, function_key, indent + 1)
        
        # Closing the body of the while loop
        func_ref.lines[node.body[-1].end_lineno].code_str += "\n" \
                                                             + indent * cline.CPPCodeLine.tab_delimiter \
                                                             + "}"
                                                             
    def parse_Pass(self, node, file_index, function_key, indent):
        """
        Handles parsing an ast.Pass node. We don't translate this
        so we just pass on calls to it

        Parameters
        ----------
        node : ast.Pass
            The ast.Pass node to be translated
        file_index : int
            Index of the file to write to in the output_files list
        function_key : str
            Key used to find the correct function in the function dictionary
        indent : int
            How much indentation a line should have
        """
        pass        
    
                                               
    def parse_Break(self, node, file_index, function_key, indent):
        """
        Handles parsing an ast.Break node.

        Parameters
        ----------
        node : ast.Break
            The ast.Break node to be translated
        file_index : int
            Index of the file to write to in the output_files list
        function_key : str
            Key used to find the correct function in the function dictionary
        indent : int
            How much indentation a line should have
        """
        func_ref = self.output_files[file_index].functions[function_key]
        func_ref.lines[node.lineno] = cline.CPPCodeLine(node.lineno,
                                                        node.end_lineno,
                                                        node.end_col_offset,
                                                        indent,
                                                        "break;")
        
    def parse_Continue(self, node, file_index, function_key, indent):
        """
        Handles parsing an ast.Continue node.

        Parameters
        ----------
        node : ast.Continue
            The ast.Continue node to be translated
        file_index : int
            Index of the file to write to in the output_files list
        function_key : str
            Key used to find the correct function in the function dictionary
        indent : int
            How much indentation a line should have
        """
        func_ref = self.output_files[file_index].functions[function_key]
        func_ref.lines[node.lineno] = cline.CPPCodeLine(node.lineno,
                                                        node.end_lineno,
                                                        node.end_col_offset,
                                                        indent,
                                                        "continue;")
        
    
    def parse_Return(self, node, file_index, function_key, indent):
        """
        Handles parsing an ast.Return node.

        Parameters
        ----------
        node : ast.Return
            The ast.Return node to be translated
        file_index : int
            Index of the file to write to in the output_files list
        function_key : str
            Key used to find the correct function in the function dictionary
        indent : int
            How much indentation a line should have
        """
        func_ref = self.output_files[file_index].functions[function_key]
        if node.value is None:
            func_ref.lines[node.lineno] = cline.CPPCodeLine(node.lineno,
                                                            node.end_lineno,
                                                            node.end_col_offset,
                                                            indent, "return;")
        else:
            try:
                return_str, return_type = self.recurse_operator(node.value,
                                                                file_index,
                                                                function_key)
            except pcex.TranslationNotSupported as ex:
                self.parse_unhandled(node, file_index, function_key, indent,
                                     ex.reason)
                return

            func_ref.return_type = self.type_precedence(return_type,
                                                        func_ref.return_type)
            func_ref.lines[node.lineno] = cline.CPPCodeLine(node.lineno,
                                                            node.end_lineno,
                                                            node.end_col_offset,
                                                            indent,
                                                            "return " + return_str + ";")
    def convert_docstring(self, doc_string, indent):
        """
        Converts a python docstring to a C++ multiline comment

        Parameters
        ----------
        doc_string : str
            The python docstring
        indent : int
            How much indentation the docstring needs

        Returns
        -------
        str
            The python docstring converted to a C++ multiline comment
        """
        # We remove the preceding whitespace as we will add our own later
        doc_string = doc_string.strip()
        tab_char = cline.CPPCodeLine.tab_delimiter
        return_str = "/*\n"

        # Every line of the docstring will need the indentation added
        while doc_string.find("\n") > -1:
            doc_string = doc_string.lstrip()
            return_str += (tab_char * indent) + doc_string[:doc_string.find("\n")] + "\n"
            doc_string = doc_string[doc_string.find("\n") + 1:]

        # Adds the last piece of the docstring
        doc_string = doc_string.lstrip()
        return_str += tab_char * indent + doc_string
        return return_str + "\n" + (tab_char * indent) + "*/"
    
    
    def parse_Expr(self, node, file_index, function_key, indent):
        """
        Handles parsing an ast.Expr node.

        Parameters
        ----------
        node : ast.Expr
            The ast.Expr node to be translated
        file_index : int
            Index of the file to write to in the output_files list
        function_key : str
            Key used to find the correct function in the function dictionary
        indent : int
            How much indentation a line should have
        """
        func_ref = self.output_files[file_index].functions[function_key]

        # Only worrying about docstrings and function calls
        # Docstrings classified as constants in ast
        if node.value.__class__ is ast.Constant:
            if type(node.value.value) is str:
                # Verify this is a docstring
                start_chars = self.raw_lines[node.value.lineno-1].strip()[0:3]
                if start_chars == '"""' or start_chars == "'''":
                    return_str = self.convert_docstring(node.value.value,
                                                        indent)
                else:
                    self.parse_unhandled(node, file_index, function_key, indent,
                                         "TODO: Constant string not used")
                    return

            else:
                self.parse_unhandled(node, file_index, function_key, indent,
                                     "TODO: Constant not used")
                return

        elif node.value.__class__ is ast.Call:
            try:
                return_str, return_type = self.parse_Call(node.value,
                                                          file_index,
                                                          function_key)

            except pcex.TranslationNotSupported as ex:
                self.parse_unhandled(node, file_index, function_key, indent,
                                     ex.reason)
                return

            return_str += ";"

        else:
            # Any other type doesn't matter as the work it does wouldn't be
            # saved
            self.parse_unhandled(node, file_index, function_key, indent,
                                 "TODO: Value not assigned or used")
            return

        func_ref.lines[node.value.lineno] = cline.CPPCodeLine(node.value.lineno,
                                                              node.value.end_lineno,
                                                              node.end_col_offset,
                                                              indent, return_str)
        
        
    def parse_Assign (self, node, file_index, function_key,indent):
        """
        Handles parsing an ast.Assign node.

        Parameters
        ----------
        node : ast.Assign
            The ast.Assign node to be translated
        file_index : int
            Index of the file to write to in the output_files list
        function_key : str
            Key used to find the correct function in the function dictionary
        indent : int
            How much indentation a line should have

        Raises
        ------
        TranslationNotSupported
            If the python code cannot be directly translated
        """
        function_ref = self.output_files[file_index].functions[function_key]

        # Won't handle chained assignment
        if len(node.targets) > 1:
            self.parse_unhandled(node, file_index, function_key, indent,
                                 "TODO: Unable to translate chained assignment")
            return
        
        var_name = node.targets[0].id
        try:
            assign_str, assign_type = self.recurse_operator(node.value,
                                                            file_index,
                                                            function_key)
            # print(assign_str,assign_type)
        except pcex.TranslationNotSupported as ex:
            self.parse_unhandled(node, file_index, function_key, indent,
                                 ex.reason)
            return
        if(assign_type[0]=="List"):
            self.output_files[file_index].add_include_file("vector")
            vector = cvec.CPPVector(name=var_name, element_type=assign_type[1], elements=assign_str)
            function_ref.vectors[var_name] = vector
            code_str= vector.declaration()
            c_code_line = cline.CPPCodeLine(node.lineno, node.end_lineno,
                                                node.end_col_offset, indent,
                                                code_str)
        else:
            
            # Find if name exists in context
            try:
                py_var_type = self.find_var_type(var_name,
                                             file_index,
                                             function_key)

                # Verify types aren't changing or we aren't losing precision
                if py_var_type[0] != assign_type[0] \
                    and (py_var_type[0] != "float" and assign_type[0] != "int"):
                # Can't do changing types in C++
                    self.parse_unhandled(node, file_index, function_key, indent,
                                     "TODO: Refactor for C++. Variable types "
                                     "cannot change or potential loss of "
                                     "precision occurred")
                    return
                else:
                    code_str = var_name + " = " + str(assign_str) + ";"
                    c_code_line = cline.CPPCodeLine(node.lineno, node.end_lineno,
                                                node.end_col_offset, indent,
                                                code_str)
            except pcex.VariableNotFound:
                # Declaration
                # print(var_name,assign_type)
                c_var = cvar.CPPVariable(var_name, node.lineno, assign_type)
                function_ref.variables[var_name] = c_var
                code_str = var_name + " = " + str(assign_str) + ";"
                c_code_line = cline.CPPCodeLine(node.lineno, node.end_lineno,
                                            node.end_col_offset, indent,
                                            code_str)

        function_ref.lines[node.lineno] = c_code_line
        
    def parse_Call(self, node, file_index, function_key):
        """
        Handles parsing an ast.Call node.

        Parameters
        ----------
        node : ast.Call
            The ast.Call node to be translated
        file_index : int
            Index of the file to write to in the output_files list
        function_key : str
            Key used to find the correct function in the function dictionary

        Returns
        -------
        return_str : str
            The call represented as a string
        return_type : list of str
            The return type of the call

        Raises
        ------
        TranslationNotSupported
            If the python code cannot be directly translated
        """
        if node.func.__class__ is not ast.Name:
            raise pcex.TranslationNotSupported("TODO: Not a valid call")
        
        # Get a reference to current function to shorten code width
        func_ref = self.output_files[file_index].functions
        func_name = node.func.id
        
        # Ensure this is a valid function call we can use
        if func_name not in cvar.CPPVariable.types \
            and func_name not in func_ref \
                and func_name not in self.ported_functions:
            raise pcex.TranslationNotSupported("TODO: Call to function not in scope")

        # We track the types passed in to help update parameter types when
        # functions get called
        arg_types = []
        arg_list = []
        for arg in node.args:
            arg_str, arg_type = self.recurse_operator(arg,
                                                      file_index,
                                                      function_key)
            arg_list.append(arg_str)
            arg_types.append(arg_type)
            
        # Check if casting or normal function call
        if func_name in cvar.CPPVariable.types:
            # Trim the extra space since we are performing a cast rather than
            # a variable declaration
            if (func_name == "str"):
                return_str = "std::to_string("
                self.output_files[file_index].add_include_file("string")
                return_type = ["str"]
            else:
                return_str = "(" + cvar.CPPVariable.types[func_name][:-1] + ")("
                return_type = [func_name]
        elif func_name in func_ref:
            return_str = func_name + "("

            # Now we try to update the parameter types if applicable
            function = func_ref[func_name]
            for param, passed_type in zip(function.parameters.values(),
                                          arg_types):
                param.py_var_type[0] = self.type_precedence(param.py_var_type,
                                                         passed_type)[0]
            return_type = function.return_type

        elif func_name in self.ported_functions:
            return self.parse_ported_function(file_index, function_key,
                                              func_name, arg_list, arg_types)

        else:
            raise pcex.TranslationNotSupported("TODO: Call to function not in scope")

        # Finish generating function call with parameters inserted
        for arg in arg_list:
            return_str += arg + ", "
        return_str = return_str[:-2] + ")"

        return return_str, return_type
    
    def parse_ported_function(self, file_index, function_key, function, args,
                              arg_types):
        """
        Converts a python version of a function to a C++ version

        Parameters
        ----------
        file_index : int
            Index of the file to write to in the output_files list
        function_key : str
            Key used to find the correct function in the function dictionary
        function : str
            Name of the function to convert
        args : list of str
            List containing the arguments represented as strings
        arg_types : list of list of str
            List containing the types of each argument in a list of str

        Returns
        -------
        return_str : str
            The ported function represented as a string
        return_type : list of str
            The return type of the ported function

        Raises
        ------
        TranslationNotSupported
            If the python code cannot be directly translated
        """
        if function == "print":
            return_str = pf.print_translation(args)
            return_type = ["None"]
            self.output_files[file_index].add_include_file("iostream")

        elif function == "sqrt":
            if len(args) > 1:
                raise pcex.TranslationNotSupported("TODO: Can't square more than 1 item")
            return_str = pf.sqrt_translation(args)
            return_type = ["float"]
            self.output_files[file_index].add_include_file("math.h")

        return return_str, return_type
    
    def parse_Constant(self, node, file_index, function_key):
        """
        Handles parsing an ast.Constant node.

        Parameters
        ----------
        node : ast.Constant
            The ast.Constant node to be translated
        file_index : int
            Index of the file to write to in the output_files list
        function_key : str
            Key used to find the correct function in the function dictionary

        Returns
        -------
        return_str : str
            The constant value represented as a string
        return_type : list of str
            The type of the constant
        """
        # Strings need to be wrapped in quotes
        if type(node.value) is str:
            self.output_files[file_index].add_include_file("string")
            return_str = ("\"" + node.value + "\"")
            return_type = ["str"]

        # Python booleans are capital while C++ is lowercase, so we need to
        # translate it
        elif type(node.value) is bool:
            return_str = cvar.CPPVariable.bool_map[str(node.value)]
            return_type = ["bool"]

        else:
            return_str = str(node.value)
            return_type = [type(node.value).__name__]

        return return_str, return_type
    
    
     # Operators
    def parse_BoolOp(self, node, file_index, function_key):
        """
        Handles parsing an ast.BoolOp node.

        Parameters
        ----------
        node : ast.BoolOp
            The ast.BoolOp node to be translated
        file_index : int
            Index of the file to write to in the output_files list
        function_key : str
            Key used to find the correct function in the function dictionary

        Returns
        -------
        return_str : str
            The BoolOp represented as a string
        return_type : list of str
            The return type of the BoolOp

        Raises
        ------
        TranslationNotSupported
            If the python code cannot be directly translated
        """
        # List of tuples consisting of (string,[type_string])
        compare_nodes = []
        mixed_types = False
        # Multiple nodes can be chained, so we need to go through all of them
        for internal_node in node.values:
            compare_nodes.append(self.recurse_operator(internal_node,
                                                       file_index,
                                                       function_key))

        # This shouldn't be possible normally, but we check to be safe
        if len(compare_nodes) < 2:
            raise pcex.TranslationNotSupported("TODO: Less than 2 items being compared")

        return_str = ""
        ret_var_type = compare_nodes[0][1][0]
        
        # Go through all but the last one and create a string separated by
        # the C++ version of the python operator
        for compare_node in compare_nodes[:-1]:
            if compare_node[1][0] != ret_var_type:
                mixed_types = True
            return_str += (compare_node[0] +
                           PyAnalyzer.operator_map[node.op.__class__.__name__])

        if compare_nodes[-1][1][0] != ret_var_type:
            mixed_types = True
        return_str += compare_nodes[-1][0]
        
        # Short circuit operators complicate type determination, so if they
        # aren't all the same type, we'll use auto, otherwise these operators
        # keep they type if all items being compared are the same type
        
        if mixed_types:
            return_type = ["auto"]
        else:
            return_type = compare_nodes[0][1]
            
        return_str = "(" + return_str + ")"
        return return_str, return_type  
    
      
    def parse_BinOp(self, node, file_index, function_key):
        """
        Handles parsing an ast.BinOp node.

        Parameters
        ----------
        node : ast.BinOp
            The ast.BinOp node to be translated
        file_index : int
            Index of the file to write to in the output_files list
        function_key : str
            Key used to find the correct function in the function dictionary

        Returns
        -------
        return_str : str
            The BinOp represented as a string
        return_type : list of str
            The return type of the BinOp

        Raises
        ------
        TranslationNotSupported
            If the python code cannot be directly translated
        """
        left_str, left_type = self.recurse_operator(node.left,
                                                    file_index,
                                                    function_key)
        right_str, right_type = self.recurse_operator(node.right,
                                                      file_index,
                                                      function_key)

        left_str = str(left_str)
        right_str = str(right_str)
        operator = node.op.__class__.__name__
        if operator in PyAnalyzer.operator_map:
            if operator == "Pow":
                self.output_files[file_index].add_include_file("math.h")
                return_str = "pow(" + left_str + ", " + right_str + ")"
                return_type = ["float"]

            elif operator == "FloorDiv":
                return_str = left_str + " / " + right_str
                # If they aren't both ints, we need to cast to int to truncate
                if left_type[0] != "int" or right_type[0] != "int":
                    return_str = "(int)(" + return_str + ")"
                return_type = ["int"]

            elif operator == "Div":
                return_str = left_str + " / " + right_str
                # We need to cast one to a double or it will perform integer
                # math
                if left_type[0] != "float" or right_type[0] != "float":
                    return_str = "(double)" + return_str
                return_type = ["float"]

            else:
                return_str = left_str \
                              + PyAnalyzer.operator_map[operator] \
                              + right_str

                return_type = self.type_precedence(left_type, right_type)

        return_str = "(" + return_str + ")"
        return return_str, return_type
    
    def type_precedence(self, type_a, type_b):
        """
        We determine which type takes precedent based on loss of
        precision. So a float will take precedence over an int
        If we can't figure it out, we'll default to auto

        Parameters
        ----------
        type_a : list of str
            One of the types to compare
        type_b : list of str
            The other type to compare with

        Returns
        -------
        return_type : list of str
            The list that holds the type that should take precedence
        """
        if type_a[0] in PyAnalyzer.type_precedence_dict and type_b[0] in PyAnalyzer.type_precedence_dict:

            # Smaller value means higher precedence
            if PyAnalyzer.type_precedence_dict[type_a[0]] < PyAnalyzer.type_precedence_dict[type_b[0]]:
                return_type = type_a

            else:
                return_type = type_b

        else:
            # Type doesn't exist in our precedence table
            return_type = ["auto"]

        return return_type
    
    def parse_UnaryOp(self, node, file_index, function_key):
        """
        Handles parsing an ast.UnaryOp node.

        Parameters
        ----------
        node : ast.UnaryOp
            The ast.UnaryOp node to be translated
        file_index : int
            Index of the file to write to in the output_files list
        function_key : str
            Key used to find the correct function in the function dictionary

        Returns
        -------
        return_str : str
            The UnaryOp represented as a string
        return_type : list of str
            The return type of the UnaryOp

        Raises
        ------
        TranslationNotSupported
            If the python code cannot be directly translated
        """
        operator = node.op.__class__
        if operator.__name__ not in PyAnalyzer.operator_map:
            raise pcex.TranslationNotSupported("TODO: UnaryOp not supported")

        return_str, return_type = self.recurse_operator(node.operand,
                                                        file_index,
                                                        function_key)

        # Not operation becomes a bool no matter what type it operated on
        if operator is ast.Not:
            return_type = ["bool"]
        else:
            return_type = ["int"]

        return_str = "(" + PyAnalyzer.operator_map[operator.__name__] + return_str + ")"
        return return_str, return_type
    
    
    def parse_Compare(self, node, file_index, function_key):
        """
        Handles parsing an ast.Compare node.

        Parameters
        ----------
        node : ast.Compare
            The ast.Compare node to be translated
        file_index : int
            Index of the file to write to in the output_files list
        function_key : str
            Key used to find the correct function in the function dictionary

        Returns
        -------
        return_str : str
            The Compare operation represented as a string
        return_type : list of str
            The return type of the Compare operation

        Raises
        ------
        TranslationNotSupported
            If the python code cannot be directly translated
        """
        # Ensure we can do all types of operations present in code line
        for op in node.ops:
            if op.__class__.__name__ not in PyAnalyzer.comparison_map:
                raise pcex.TranslationNotSupported("TODO: Comparison operation not supported")

        # Comparisons can be chained, so we use the left item as the
        # "last" item to be compared to start the chain
        last_comparator = self.recurse_operator(node.left,
                                                file_index,
                                                function_key)[0]

        return_str = ""
        # Chaining comparisons together with ands
        for index in range(1, len(node.ops)-1):
            comparator = self.recurse_operator(node.comparators[index],
                                               file_index,
                                               function_key)[0]
            return_str += "(" + last_comparator \
                          + PyAnalyzer.comparison_map[node.ops[index-1].__class__.__name__] \
                          + comparator + ") && "
            last_comparator = comparator

        # Add last comparison on the end
        comparator = self.recurse_operator(node.comparators[-1],
                                           file_index,
                                           function_key)[0]

        return_str += "(" + last_comparator + \
                      PyAnalyzer.comparison_map[node.ops[-1].__class__.__name__] \
                      + comparator + ")"

        # All comparisons come back as a bool
        return_type = ["bool"]
        return return_str, return_type
    
    def recurse_operator(self, node, file_index, function_key):
        """
        Accepts a node and determines the appropriate handler function to use
        then passes the parameters to the correct handler function. Called
        recursively to parse through code lines

        Parameters
        ----------
        node : ast node
            The ast node to be translated
        file_index : int
            Index of the file to write to in the output_files list
        function_key : str
            Key used to find the correct function in the function dictionary

        Returns
        -------
        tuple : (str, [str])
            Tuple with the string representation of the operation and the
            return type in a list of a string

        Raises
        ------
        TranslationNotSupported
            If the python code cannot be directly translated
        """
        
        node_type = node.__class__
        if node_type is ast.BinOp:
            return self.parse_BinOp(node, file_index, function_key)

        elif node_type is ast.BoolOp:
            return self.parse_BoolOp(node, file_index, function_key)

        elif node_type is ast.UnaryOp:
            return self.parse_UnaryOp(node, file_index, function_key)

        elif node_type is ast.Compare:
            return self.parse_Compare(node, file_index, function_key)

        elif node_type is ast.Call:
            return self.parse_Call(node, file_index, function_key)

        elif node_type is ast.Name:
            # Variable should already exist if we're using it, so we just grab
            # it from the current context
            try:
                return node.id, self.find_var_type(node.id,
                                                   file_index,
                                                   function_key)
            except pcex.VariableNotFound:
                # Can't handle non declared variables being used
                raise pcex.TranslationNotSupported("TODO: Variable used before declaration")

        elif node_type is ast.Constant:
            return self.parse_Constant(node, file_index, function_key)
        
        elif node_type is ast.List:
            return self.parse_List(node,file_index,function_key)
        elif node_type is ast.Subscript:
            try:
                return self.parse_Subscript(node,file_index,function_key)
            except pcex.VariableNotFound:
                raise pcex.TranslationNotSupported("TODO: Variable used before declaration")


        else:
            # Anything we don't handle
            raise pcex.TranslationNotSupported()
        
        
     # Helper methods
    def find_var_type(self, name, file_index, function_key):
        """
        Finds the type of a variable in a given context

        Parameters
        ----------
        name : str
            Name of the variable to find
        file_index : int
            Index of the file to find the variable
        function_key : str
            Key used to find the correct function in the function dictionary

        Returns
        -------
        list : list of str
            The list reference containing the variable type

        Raises
        ------
        VariableNotFound
            If the variable can't be found in the given context
        """
        function_ref = self.output_files[file_index].functions[function_key]

        if name in function_ref.parameters:
            return function_ref.parameters[name].py_var_type

        elif name in function_ref.variables:
            return function_ref.variables[name].py_var_type

        else:
            raise pcex.VariableNotFound()
    
    def parse_List(self, node, file_index, function_key):
        """
        Handles parsing an ast.List node into a CPPVector.

        Parameters
        ----------
        node : ast.List
            The ast.List node to be translated.
        file_index : int
            Index of the file to write to in the output_files list.
        function_key : str
            Key used to find the correct function in the function dictionary.
        indent : int
            How much indentation a line should have.
        """
        func_ref = self.output_files[file_index].functions[function_key]

        # Parse elements of the list
        elements = [self.recurse_operator(el, file_index, function_key) for el in node.elts]
         # Extract data types and values
        values = [el[0] for el in elements]
        types = [el[1][0] for el in elements]  

        # Check if all types are the same
        common_type = types[0]
        all_same_type = all(t == common_type for t in types)
        
        if all_same_type:
            element_type=cvar.CPPVariable.types[common_type].strip()
        else:
            raise pcex.TranslationNotSupported("TODO : Hetrogeneous Lists Not Supported")

        
        return values,["List",element_type]
    
    
    def parse_Subscript(self, node, file_index, function_key):
        """
        Handles parsing an ast.Subscript node for list indexing.

        Parameters
        ----------
        node : ast.Subscript
            The ast.Subscript node to be translated.
        file_index : int
            Index of the file to write to in the output_files list.
        function_key : str
            Key used to find the correct function in the function dictionary.
        indent : int
            How much indentation a line should have.
        """
        func_ref = self.output_files[file_index].functions[function_key]

        list_name = func_ref.vectors.get(node.value.id)
        if list_name is None:
            raise pcex.VariableNotFound()

        index = self.recurse_operator(node.slice, file_index, function_key)[0]
        # print(index)
        if index is None:
            raise pcex.TranslationNotSupported("TODO: Range query on vector")

        
        # Generate the C++ code for element access
        access_code = f"{list_name.name}[{index}]"
        
        # print(access_code,list_name.element_type)
        return access_code,list_name.element_type

class CPPVariable():
    """
    This class represents a variable, holding information about it to be used
    while outputting to the C++ file
    """
    
    # Using redundant mapping to allow for changes to mapped type
    types = {
             "int": "int ", "float": "double ", "str": "std::string ",
             "bool": "bool ", "None": "NULL", "char **": "char **",
             "void": "void ", "auto": "auto ", "NoneType": "void "
             }
    
    # Python uses capital letters while C++ uses lowercase
    bool_map = {"True": "true", "False": "false"}
    
    def __init__(self, name, line_num, py_var_type):
        """
        Constructs a C++ variable object representation converted from python

        Parameters
        ----------
        name : str
            The name of the variable
        line_num : int
            The line number this variable was declared on in python
        py_var_type : list of str
            The type of the variable in python
        """
        self.name = name
        self.line_num= line_num
        
        # We use a list here to get a mutable type
        self.py_var_type = py_var_type
class cvar:
    CPPVariable=CPPVariable 
    
class CPPCodeLine():
    """
    Class to represent a line of code in C++
    """
    # Using a variable in case we want to use tabs instead of spaces
    tab_delimiter = "    "
    
    def __init__(self, start_line_num, end_line_num, end_char_index,
                 indent, code_str="", comment_str="", pre_comment_str=""):
        """
        Constructs a CPPLine object

        Parameters
        ----------
        start_line_num : int
            Line number the code starts on in the python file
        end_line_num : int
            Line number the code ends on in the python file
        end_char_index : int
             Index of the last character in this line in the python file
        indent : int
            Amount to indent the line by in the C++ file
        code_str : str
            The text for this line of C++ code
        comment_str : str
            The text for any inline comments, if applicable
        pre_comment_str : str
            The text for any comment that should precede this line of code, if
            applicable
        """
        
        # Line in the original python script
        self.start_line_num = start_line_num

        # Allows us to handle multiline code lines
        self.end_line_num = end_line_num

        # Tells us where to start searching for inline comments, if any
        self.end_char_index = end_char_index

        # How much to indent the line in the C++ file
        self.indent = indent

        # String containing the converted C++ code
        self.code_str = code_str

        # String containing any inline comments
        # Also applicable if it is a comment only line, the code_str field
        # will just be an empty string
        self.comment_str = comment_str

        # String containing a comment that should precede a line of code
        # Used to help put comments about a line of code that couldn't be
        # converted
        self.pre_comment_str = pre_comment_str
        
    def get_formatted_code_line(self):
        """
        Generates a string representation of this C++ code line object

        Returns
        -------
        str
            A string with the converted C++ code
        """
        return_str = ""
        # Goes through various permutations of how this object could be
        # populated. We need different handlers to ensure indentation is done
        # correctly
        if self.pre_comment_str != "":
            return_str += CPPCodeLine.tab_delimiter * self.indent \
                          + "//" + self.pre_comment_str + "\n"
        
        if self.code_str != "":
            # Standard code line
            return_str += CPPCodeLine.tab_delimiter * self.indent \
                          + self.code_str
            if self.comment_str != "":
                # Inline comment as well
                return_str += CPPCodeLine.tab_delimiter \
                              + "//" + self.comment_str
                              
        elif self.comment_str != "":
            # Only a comment present
            return_str += CPPCodeLine.tab_delimiter * self.indent \
                          + "//" + self.comment_str
                          
        else:
            # Empty line
            return_str += CPPCodeLine.tab_delimiter * self.indent
            
        return return_str        
class cline:
    CPPCodeLine=CPPCodeLine
    
class CPPFile():
    """
    Class to represent a C++ file that will be exported
    """
    
    def __init__(self,filename):
        """
        Constructs a CPPFile object

        Parameters
        ----------
        filename : str
            Name for the file
        """
        # Includes are just strings of name of include file
        self.includes=[]
        
        # Stored as a dictionary of {Function Name: CPPFunction object}
        self.functions = {}
        
        self.filename = filename
        
    def add_include_file(self, file):
        """
        Adds the provided include file to the current cpp file if it doesn't
        already exist

        Parameters
        ----------
        file : str
            Name of the include file to add
        """
        if file not in self.includes:
            self.includes.append(file)
            
    def get_formatted_file_text(self):
        """
        Generates the text representing the entire C++ file

        Returns
        -------
        return_str : str
            The text of the converted C++ file
        """
        return_str= ""
        
        for file in self.includes:
            return_str+= "#include <"+ file + ">\n"
            
        return_str += "\n"
        
        # Now put in forward declarations
        # Skip main since it doesn't need a forward declaration
        for function_key in list(self.functions.keys())[1:]:
            return_str+= self.functions[function_key].get_forward_declaration() + ";\n"
            
        return_str +="\n"
        
        # Now we put in all of the functions for the file
        for function in self.functions.values():
            return_str +=function.get_formatted_function_text() + "\n\n"
            
        return return_str
class cfile:
    CPPFile=CPPFile    
        
class CPPFunction():
    """
    Class to represent Python functions as C++ functions
    """
    
    def __init__(self, name, lineno, end_lineno, parameters={}):
        """
        Constructs a CPPFunction object

        Parameters
        ----------
        name : str
            The name of the function
        lineno : int
            The line where the function is declared in the python file
        end_lineno : int
            The line where the function ends in the python file
        parameters : dict of {str: CPPVariable}
            The parameters this function has passed in
        """
        
        self.name= name
        
        # We store these to help with performing the comment and blank line
        # pass on the script file to know where to put the lines
        # Note: doesn't apply for the main function which takes code from
        # anywhere in the file
        self.lineno = lineno
        self.end_lineno = end_lineno
        
        # Provides a lookup table for parameters, allowing for type updates
        # as file is parsed
        # Dictionary of {Variable Name : CPPVariable Object}
        self.parameters = parameters
        
        
        # Lines in a function stored as a dictionary of format
        # {LineNumber : CPPCodeLine} where line number is an int of the line
        # number in the python script
        self.lines = {}
        
        # Provides a lookup table for variables declared in the scope,
        # allowing for type updates as the file is parsed
        # Dictionary of Variable Name : CPPVariable Object
        self.variables = {}
        
        self.vectors= {}
        
        # Using a list so type gets updated if more information is found about
        # a related variable
        self.return_type = ["void"]
        
    def get_forward_declaration(self):
        """
        Generates the string representation of this function's forward
        declaration. This is separate from get signature because we don't
        want to include any default values in the forward declaration

        Returns
        -------
        str
            The function's forward declaration
        """
        
        function_signature = cvar.CPPVariable.types[self.return_type[0]]
        function_signature += self.name + "("
        
        if len(self.parameters) > 0:
            for parameter in self.parameters:
                function_signature += cvar.CPPVariable.types[self.parameters[parameter].py_var_type[0]]
                function_signature += parameter + ", "
            function_signature = function_signature[:-2]
            
        return function_signature + ")"
    
    def get_signature(self):
        """
        Generates the string representation of this function's signature

        Returns
        -------
        str
            The function's signature
        """
        function_signature = cvar.CPPVariable.types[self.return_type[0]]
        # Convert internally named main function to proper name
        if self.name == "0":
            function_signature += "main("
        else:
            function_signature += self.name + "("

        # Check if there are any parameters before attempting to add them
        if len(self.parameters.values()) > 0:
            for parameter in self.parameters.values():
                # Prepend the param type in C++ style before the param name
                function_signature += cvar.CPPVariable.types[parameter.py_var_type[0]]
                function_signature += parameter.name + ", "

            # Remove the extra comma and space
            function_signature = function_signature[:-2]

        return function_signature + ")"
    
    def get_formatted_function_text(self):
        """
        Generates a string with all of this function's code within it

        :return: String containing all of the function's C++ code
        """
        return_str = ""

        # First line is the function signature
        return_str += self.get_signature() + "\n{\n"

        # Go through all lines and get their formatted string version and
        # append to the string we will return
        for line in self.lines.values():
            return_str += line.get_formatted_code_line() + "\n"
        if(self.name=="0"):
            return_str+="\n\treturn 0;\n"
        # Add a closing bracket for the end of the function
        return return_str + "}"
class cfun:
    CPPFunction=CPPFunction 
        
    
class CPPVector:
    """
    Represents a C++ vector and provides methods to handle vector operations.
    """
    def __init__(self, name, element_type="auto", elements=None):
        """
        Initialize a CPPVector.

        Parameters:
        ----------
        name : str
            Name of the vector.
        element_type : str
            Type of elements in the vector (e.g., int, float).
        elements : list, optional
            Initial elements for the vector.
        """
        self.name = name
        self.element_type = [element_type]
        self.elements = elements or []

    def declaration(self):
        """
        Generate the C++ declaration for the vector.

        Returns:
        -------
        str
            The C++ declaration as a string.
        """
        elements_str = ", ".join(map(str, self.elements))
        return f"std::vector<{self.element_type[0]}> {self.name} = {{ {elements_str} }};"

    def access_element(self, index):
        """
        Generate C++ code to access an element by index.

        Parameters:
        ----------
        index : int or str
            Index of the element.

        Returns:
        -------
        str
            The C++ code for accessing the element.
        """
        return f"{self.name}[{index}]"
class cvec:
    CPPVector=CPPVector