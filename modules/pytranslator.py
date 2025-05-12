import ast 
from modules import pyanalyzer


class PyTranslator():
    """
    This class starts the launching of the analysis on the script and writing the analysis output
    to a usable C++ file
    """
    
    def __init__(self,script_path, output_path):
        """
        Constructor of a python to C++ translator.
        This will automatically create a main.cpp and main function for code
        
        """
        self.script_path= script_path
        self.output_path= output_path
        
        self.output_files= [cfile.CPPFile("main")]
        main_params={"argc": cvar.CPPVariable("argc",-1,["int"]),
                     "argv": cvar.CPPVariable("argv",-1,["char **"])}
        
        # We name the function 0 because that is an invalid name in python
        # Otherwise theres a chance theres a function named main already
        # At file output, this will be changed to main
        
        main_function= cfun.CPPFunction("0",-1,-1,main_params)
        main_function.return_type[0]="int"
        
        self.output_files[0].functions["0"]= main_function
        
    def write_cpp_files(self):
        """
        This performs the process of converting the object representations
        of the code into usable strings and writes them to the appropriate
        output file
        """
        # Currently only one file, but this forms a basis to allow for multi-
        # file outputs from classes in C++
        for file in self.output_files:
            try:
                f = open(self.output_path + file.filename + ".cpp", "w")
                f.write(file.get_formatted_file_text())
                f.close()
            except IOError:
                print("Error writing file: " + self.output_path
                      + file.filename + ".cpp")
        print("Output written to " + self.output_path)
        
    def ingest_comments(self,raw_lines):
        """
        Pulls comments from the original script, converts them to C++ style comments, then puts them
        into line dictionaries of their corresponding function so they are included during the
        output phase

        Parameters
        ----------
        raw_lines : list of str
            List of strings containing the original python script line by line
        """
        # First get a dictionary with every existing line of code. That way
        # we know whether to look for an inline comment or a full line comment
        
        for file in self.output_files:
            all_lines_dict={}
            for cfunction in file.functions.values():
                # -merge-two-dictionaries-in-a-single-expression-in-python
                # -taking-union-o
                all_lines_dict={**all_lines_dict,**cfunction.lines}
                
            # Going through all lines in the script we are parsing   
            for index in range(len(raw_lines)):
                # Line numbers count from 1 while list starts from 0, so we need to offset by 1
                if (index+1) in all_lines_dict:
                    # Looking fo inline comments
                    code_line=all_lines_dict[index+1]
                    comment=raw_lines[index][code_line.end_char_index:].lstrip()
                    
                    if len(comment)>0 and comment[0]=="#":
                        # Trim off the comment symbol as it will be changed
                        # to the C++ style comment
                        all_lines_dict[index+1].comment_str=comment[1:].lstrip()
                else:
                    # Determine which function the line belongs to
                    for function in file.functions.values():
                        if function.lineno< index+1< function.end_lineno:
                            line= raw_lines[index]
                            comment= line.lstrip()
                            if len(comment)>0 and comment[0]== "#":
                                # C++ uses '//' to indicate comments instead of '#'
                                comment= line.replace("#","//",1)
                                function.lines[index+1]= cline.CPPCodeLine(index+1, index+1, len(line),0,comment)
                                break
                    else:
                        line= raw_lines[index]
                        comment=line.lstrip()
                        if len(comment)>0 and comment[0]=="#":
                            # We add an extra indent on code not in a function
                            # since it will go into a function in C++
                            comment=cline.CPPCodeLine.tab_delimiter+line.replace("#","//",1)
                            file.functions["0"].lines[index+1]= cline.CPPCodeLine(index+1,index+1,len(line),0,comment)
        
        # Sort function line dictionaries so output is in proper order
        for function in file.functions.values():
            sorted_lines= {}
            for line in sorted(function.lines.keys()):
                sorted_lines[line]= function.lines[line]
            function.lines = sorted_lines
            
    def apply_variable_types(self):
        """
        Goes through every variable in every function to apply types to them
        on declaration
        """
        for file in self.output_files:
            for cfunction in file.functions.values():
                for variable in cfunction.variables.values():
                    # Need to include string library for strings in C++
                    if variable.py_var_type[0] == "str":
                        file.add_include_file("string")
                        
                    # Prepend lne with variable type to apply type
                    cfunction.lines[variable.line_num].code_str \
                        = cvar.CPPVariable.types[variable.py_var_type[0]] + cfunction.lines[variable.line_num].code_str
    
    def run(self):
        """
        Entry point for parsing a python script. This will read the script
        line by line until it reaches the end, then it will call
        write_cpp_files to export the code into a cpp file
        """
        
        file_index=0
        function_key= "0"
        
        indent=1
        
        with open(self.script_path, "r") as py_source:
            tree = ast.parse(py_source.read())
            # resets pointer
            py_source.seek(0)        
            all_lines=py_source.read().splitlines()
            
        analyzer=pyanalyzer.PyAnalyzer(self.output_files,all_lines)
        analyzer.analyze(tree.body,file_index,function_key,indent)
        
        self.apply_variable_types()
        self.ingest_comments(all_lines)
        self.write_cpp_files()
        
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
        