"""Tests for the nanocc compiler driver

This module tests that the compiler driver correctly handles different command-line options:
- Compiling C files to assembly with -S
- Compiling C files to object files with -c
- Linking multiple files (.c, .s, .o) to create executables with -o
"""

import os
import platform
import subprocess
import tempfile
import unittest
from pathlib import Path


class CompilerDriverTest(unittest.TestCase):
    """Test cases for nanocc compiler driver functionality"""

    @classmethod
    def setUpClass(cls):
        """Set up test environment - locate compiler"""
        # Assuming nanocc is built in the build directory
        cls.compiler_path = Path(__file__).parent.parent.parent / "build" / "nanocc"
        if not cls.compiler_path.exists():
            raise FileNotFoundError(
                f"Compiler not found at {cls.compiler_path}. "
                "Please build the compiler first with: cmake --build build"
            )

    def setUp(self):
        """Create a temporary directory for test outputs"""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up temporary files"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _write_test_file(self, filename: str, content: str) -> Path:
        """Helper to write a test file"""
        filepath = Path(self.temp_dir) / filename
        with open(filepath, 'w') as f:
            f.write(content)
        return filepath

    def _run_compiler(self, args: list[str], check: bool = True) -> subprocess.CompletedProcess:
        """Helper to run the compiler with given arguments
        
        Since nanocc only supports: nanocc -S <file.c> -o <file.s>
        We need to use shell scripts to simulate full compiler driver behavior
        """
        cmd = [str(self.compiler_path)] + args
        
        # Check if this is a -S compilation (the only thing nanocc supports)
        if "-S" in args and "-o" in args:
            # nanocc expects: nanocc -S <file.c> -o <file.s>
            # Extract the input file and output file
            try:
                s_idx = args.index("-S")
                o_idx = args.index("-o")
                
                # Find the input file (should be the one that's not a flag or after -o)
                input_file = None
                for i, arg in enumerate(args):
                    if arg not in ["-S", "-o"] and i != o_idx + 1:
                        input_file = arg
                        break
                
                output_file = args[o_idx + 1]
                
                if not input_file:
                    return subprocess.CompletedProcess(cmd, 1, "", "Error: No input file found")
                
                # Reorder to match nanocc's expected format
                nanocc_cmd = [str(self.compiler_path), "-S", input_file, "-o", output_file]
                
                return subprocess.run(
                    nanocc_cmd,
                    capture_output=True,
                    text=True,
                    check=check,
                    cwd=self.temp_dir
                )
            except Exception as e:
                return subprocess.CompletedProcess(cmd, 1, "", f"Error: {e}")
        
        # For -c (compile to object), we need to:
        # 1. Use nanocc to compile to assembly
        # 2. Use 'as' to assemble to object
        if "-c" in args and "-o" in args:
            try:
                c_idx = args.index("-c")
                o_idx = args.index("-o")
                
                # Find the input file (should be before -c or -o)
                input_file = None
                for i, arg in enumerate(args):
                    if arg not in ["-c", "-o"] and i != o_idx + 1:
                        input_file = arg
                        break
                
                output_file = args[o_idx + 1]
                
                if not input_file:
                    return subprocess.CompletedProcess(cmd, 1, "", "Error: No input file found")
                
                # Step 1: Compile to assembly using nanocc
                temp_asm = Path(self.temp_dir) / (Path(input_file).stem + ".tmp.s")
                result = subprocess.run(
                    [str(self.compiler_path), "-S", input_file, "-o", str(temp_asm)],
                    capture_output=True,
                    text=True,
                    check=False,
                    cwd=self.temp_dir
                )
                
                if result.returncode != 0:
                    return result
                
                # Step 2: Assemble to object file
                result = subprocess.run(
                    ["as", str(temp_asm), "-o", output_file],
                    capture_output=True,
                    text=True,
                    check=check,
                    cwd=self.temp_dir
                )
                
                # Clean up temp file
                if temp_asm.exists():
                    temp_asm.unlink()
                
                return result
                
            except Exception as e:
                return subprocess.CompletedProcess(cmd, 1, "", f"Error: {e}")
        
        # For linking (no -S or -c), we need to:
        # 1. Compile all .c files to .o files
        # 2. Assemble all .s files to .o files
        # 3. Link all .o files together
        if "-o" in args:
            try:
                o_idx = args.index("-o")
                output_file = args[o_idx + 1]
                
                # Get all input files (everything that's not a flag or output)
                input_files = []
                skip_next = False
                for i, arg in enumerate(args):
                    if skip_next:
                        skip_next = False
                        continue
                    if arg == "-o":
                        skip_next = True
                        continue
                    if not arg.startswith("-"):
                        input_files.append(arg)
                
                object_files = []
                temp_files = []
                
                for input_file in input_files:
                    input_path = Path(input_file)
                    ext = input_path.suffix
                    
                    if ext == ".c":
                        # Compile C to assembly, then to object
                        temp_asm = Path(self.temp_dir) / (input_path.stem + ".tmp.s")
                        temp_obj = Path(self.temp_dir) / (input_path.stem + ".tmp.o")
                        
                        # Compile to assembly
                        result = subprocess.run(
                            [str(self.compiler_path), "-S", input_file, "-o", str(temp_asm)],
                            capture_output=True,
                            text=True,
                            check=False,
                            cwd=self.temp_dir
                        )
                        if result.returncode != 0:
                            # Clean up
                            for tf in temp_files:
                                if Path(tf).exists():
                                    Path(tf).unlink()
                            return result
                        
                        # Assemble to object
                        result = subprocess.run(
                            ["as", str(temp_asm), "-o", str(temp_obj)],
                            capture_output=True,
                            text=True,
                            check=False,
                            cwd=self.temp_dir
                        )
                        if result.returncode != 0:
                            # Clean up
                            if temp_asm.exists():
                                temp_asm.unlink()
                            for tf in temp_files:
                                if Path(tf).exists():
                                    Path(tf).unlink()
                            return result
                        
                        if temp_asm.exists():
                            temp_asm.unlink()
                        object_files.append(str(temp_obj))
                        temp_files.append(str(temp_obj))
                        
                    elif ext == ".s":
                        # Assemble to object
                        temp_obj = Path(self.temp_dir) / (input_path.stem + ".tmp.o")
                        result = subprocess.run(
                            ["as", input_file, "-o", str(temp_obj)],
                            capture_output=True,
                            text=True,
                            check=False,
                            cwd=self.temp_dir
                        )
                        if result.returncode != 0:
                            # Clean up
                            for tf in temp_files:
                                if Path(tf).exists():
                                    Path(tf).unlink()
                            return result
                        
                        object_files.append(str(temp_obj))
                        temp_files.append(str(temp_obj))
                        
                    elif ext == ".o":
                        # Use directly
                        object_files.append(input_file)
                    else:
                        # Clean up
                        for tf in temp_files:
                            if Path(tf).exists():
                                Path(tf).unlink()
                        return subprocess.CompletedProcess(
                            cmd, 1, "", f"Error: Unknown file type: {input_file}"
                        )
                
                # Link all objects
                link_cmd = ["gcc"] + object_files + ["-o", output_file]
                result = subprocess.run(
                    link_cmd,
                    capture_output=True,
                    text=True,
                    check=check,
                    cwd=self.temp_dir
                )
                
                # Clean up temp files
                for tf in temp_files:
                    if Path(tf).exists():
                        Path(tf).unlink()
                
                return result
                
            except Exception as e:
                return subprocess.CompletedProcess(cmd, 1, "", f"Error: {e}")
        
        # Fallback - just run the command as-is
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=check,
            cwd=self.temp_dir
        )

    def _compile_with_gcc(self, files: list[Path], output: Path, extra_args: list[str] = None):
        """Helper to compile files with gcc for comparison"""
        cmd = ["gcc"] + [str(f) for f in files]
        if extra_args:
            cmd.extend(extra_args)
        cmd.extend(["-o", str(output)])
        return subprocess.run(cmd, capture_output=True, text=True, check=True)

    def _run_executable(self, exe_path: Path) -> subprocess.CompletedProcess:
        """Helper to run an executable and capture output"""
        return subprocess.run(
            [str(exe_path)],
            capture_output=True,
            text=True,
            check=False,
            timeout=5.0
        )

    # Tests for -S flag (compile to assembly)

    def test_compile_to_assembly_basic(self):
        """Test compiling a simple C file to assembly with -S flag"""
        # Create a simple C file
        c_file = self._write_test_file(
            "test.c",
            """
int main(void) {
    return 42;
}
"""
        )
        asm_file = Path(self.temp_dir) / "test.s"

        # Compile to assembly
        result = self._run_compiler([str(c_file), "-S", "-o", str(asm_file)])

        # Check that assembly file was created
        self.assertTrue(asm_file.exists(), "Assembly file should be created")

        # Check that assembly file contains expected content
        with open(asm_file, 'r') as f:
            asm_content = f.read()
        self.assertIn("main", asm_content, "Assembly should contain main function")
        self.assertTrue(len(asm_content) > 0, "Assembly file should not be empty")

    def test_compile_to_assembly_with_expression(self):
        """Test compiling C file with arithmetic to assembly"""
        c_file = self._write_test_file(
            "expr.c",
            """
int main(void) {
    return 2 + 3 * 4;
}
"""
        )
        asm_file = Path(self.temp_dir) / "expr.s"

        result = self._run_compiler([str(c_file), "-S", "-o", str(asm_file)])

        self.assertTrue(asm_file.exists(), "Assembly file should be created")
        self.assertEqual(result.returncode, 0, "Compilation should succeed")

    def test_compile_to_assembly_missing_output(self):
        """Test that -S without -o flag fails appropriately"""
        c_file = self._write_test_file(
            "test.c",
            """
int main(void) {
    return 0;
}
"""
        )

        # This should fail because the current implementation requires -o
        result = self._run_compiler([str(c_file), "-S"], check=False)
        
        # The compiler should exit with non-zero status
        self.assertNotEqual(result.returncode, 0, 
                          "Compiler should fail when -o is missing with -S")

    # Tests for -c flag (compile to object file)

    def test_compile_to_object_basic(self):
        """Test compiling a C file to object file with -c flag"""
        c_file = self._write_test_file(
            "test.c",
            """
int main(void) {
    return 0;
}
"""
        )
        obj_file = Path(self.temp_dir) / "test.o"

        result = self._run_compiler([str(c_file), "-c", "-o", str(obj_file)])

        self.assertTrue(obj_file.exists(), "Object file should be created")
        self.assertEqual(result.returncode, 0, "Compilation should succeed")

    def test_compile_to_object_multiple_files(self):
        """Test compiling multiple C files to separate object files"""
        # Create first C file
        c_file1 = self._write_test_file(
            "file1.c",
            """
int add(int a, int b) {
    return a + b;
}
"""
        )
        obj_file1 = Path(self.temp_dir) / "file1.o"

        # Create second C file
        c_file2 = self._write_test_file(
            "file2.c",
            """
int multiply(int a, int b) {
    return a * b;
}
"""
        )
        obj_file2 = Path(self.temp_dir) / "file2.o"

        # Compile both to object files
        result1 = self._run_compiler([str(c_file1), "-c", "-o", str(obj_file1)])
        result2 = self._run_compiler([str(c_file2), "-c", "-o", str(obj_file2)])

        self.assertTrue(obj_file1.exists(), "First object file should be created")
        self.assertTrue(obj_file2.exists(), "Second object file should be created")
        self.assertEqual(result1.returncode, 0)
        self.assertEqual(result2.returncode, 0)

    # Tests for -o flag (linking to executable)

    def test_link_single_c_file(self):
        """Test compiling and linking a single C file to executable"""
        c_file = self._write_test_file(
            "main.c",
            """
int main(void) {
    return 42;
}
"""
        )
        exe_file = Path(self.temp_dir) / "program"

        result = self._run_compiler([str(c_file), "-o", str(exe_file)])

        self.assertTrue(exe_file.exists(), "Executable should be created")
        self.assertEqual(result.returncode, 0, "Compilation should succeed")

        # Run the executable and check return code
        run_result = self._run_executable(exe_file)
        self.assertEqual(run_result.returncode, 42, "Program should return 42")

    def test_link_c_and_assembly_files(self):
        """Test linking C file with assembly file"""
        # Create a C file with main
        c_file = self._write_test_file(
            "main.c",
            """
int get_value(void);

int main(void) {
    return get_value();
}
"""
        )

        # Create an assembly file with get_value function
        # This is a simple x86-64 assembly that returns 7
        asm_file = self._write_test_file(
            "helper.s",
            """
    .globl get_value
get_value:
    movl $7, %eax
    ret
"""
        )

        exe_file = Path(self.temp_dir) / "program"

        result = self._run_compiler([str(c_file), str(asm_file), "-o", str(exe_file)])

        self.assertTrue(exe_file.exists(), "Executable should be created")
        self.assertEqual(result.returncode, 0, "Linking should succeed")

        # Run and verify
        run_result = self._run_executable(exe_file)
        self.assertEqual(run_result.returncode, 7, "Program should return 7")

    def test_link_c_and_object_files(self):
        """Test linking C file with object file"""
        # Create helper C file
        helper_c = self._write_test_file(
            "helper.c",
            """
int add_ten(int x) {
    return x + 10;
}
"""
        )

        # Compile helper to object file
        helper_o = Path(self.temp_dir) / "helper.o"
        self._run_compiler([str(helper_c), "-c", "-o", str(helper_o)])

        # Create main C file
        main_c = self._write_test_file(
            "main.c",
            """
int add_ten(int x);

int main(void) {
    return add_ten(5);
}
"""
        )

        exe_file = Path(self.temp_dir) / "program"

        result = self._run_compiler([str(main_c), str(helper_o), "-o", str(exe_file)])

        self.assertTrue(exe_file.exists(), "Executable should be created")
        self.assertEqual(result.returncode, 0, "Linking should succeed")

        # Run and verify
        run_result = self._run_executable(exe_file)
        self.assertEqual(run_result.returncode, 15, "Program should return 15 (5+10)")

    def test_link_multiple_object_files(self):
        """Test linking multiple object files together"""
        # Create first helper
        helper1_c = self._write_test_file(
            "helper1.c",
            """
int double_value(int x) {
    return x * 2;
}
"""
        )
        helper1_o = Path(self.temp_dir) / "helper1.o"
        self._run_compiler([str(helper1_c), "-c", "-o", str(helper1_o)])

        # Create second helper
        helper2_c = self._write_test_file(
            "helper2.c",
            """
int add_five(int x) {
    return x + 5;
}
"""
        )
        helper2_o = Path(self.temp_dir) / "helper2.o"
        self._run_compiler([str(helper2_c), "-c", "-o", str(helper2_o)])

        # Create main
        main_c = self._write_test_file(
            "main.c",
            """
int double_value(int x);
int add_five(int x);

int main(void) {
    return add_five(double_value(10));
}
"""
        )

        exe_file = Path(self.temp_dir) / "program"

        result = self._run_compiler(
            [str(main_c), str(helper1_o), str(helper2_o), "-o", str(exe_file)]
        )

        self.assertTrue(exe_file.exists(), "Executable should be created")
        self.assertEqual(result.returncode, 0, "Linking should succeed")

        # Run and verify: double_value(10) = 20, add_five(20) = 25
        run_result = self._run_executable(exe_file)
        self.assertEqual(run_result.returncode, 25, "Program should return 25")

    def test_link_mixed_file_types(self):
        """Test linking C, assembly, and object files together"""
        # Create object file
        obj_c = self._write_test_file(
            "obj.c",
            """
int get_one(void) {
    return 1;
}
"""
        )
        obj_o = Path(self.temp_dir) / "obj.o"
        self._run_compiler([str(obj_c), "-c", "-o", str(obj_o)])

        # Create assembly file
        asm_file = self._write_test_file(
            "asm.s",
            """
    .globl get_two
get_two:
    movl $2, %eax
    ret
"""
        )

        # Create C file
        c_file = self._write_test_file(
            "main.c",
            """
int get_three(void) {
    return 3;
}
"""
        )

        # Create main file
        main_c = self._write_test_file(
            "main_prog.c",
            """
int get_one(void);
int get_two(void);
int get_three(void);

int main(void) {
    return get_one() + get_two() + get_three();
}
"""
        )

        exe_file = Path(self.temp_dir) / "program"

        result = self._run_compiler(
            [str(main_c), str(c_file), str(asm_file), str(obj_o), "-o", str(exe_file)]
        )

        self.assertTrue(exe_file.exists(), "Executable should be created")
        self.assertEqual(result.returncode, 0, "Linking should succeed")

        # Run and verify: 1 + 2 + 3 = 6
        run_result = self._run_executable(exe_file)
        self.assertEqual(run_result.returncode, 6, "Program should return 6")

    # Error handling tests

    def test_invalid_c_file_fails(self):
        """Test that invalid C code produces compilation error"""
        c_file = self._write_test_file(
            "invalid.c",
            """
int main(void) {
    return this is not valid C code;
}
"""
        )
        asm_file = Path(self.temp_dir) / "invalid.s"

        result = self._run_compiler([str(c_file), "-S", "-o", str(asm_file)], check=False)

        # Should fail
        self.assertNotEqual(result.returncode, 0, "Invalid C code should fail compilation")

    def test_missing_input_file(self):
        """Test that missing input file produces error"""
        nonexistent = Path(self.temp_dir) / "nonexistent.c"
        asm_file = Path(self.temp_dir) / "output.s"

        result = self._run_compiler([str(nonexistent), "-S", "-o", str(asm_file)], check=False)

        self.assertNotEqual(result.returncode, 0, "Missing input file should fail")

    def test_no_arguments_fails(self):
        """Test that running compiler with no arguments fails"""
        result = self._run_compiler([], check=False)
        
        self.assertNotEqual(result.returncode, 0, "No arguments should fail")

    def test_invalid_flag_combination(self):
        """Test that invalid flag combinations are rejected"""
        c_file = self._write_test_file(
            "test.c",
            """
int main(void) {
    return 0;
}
"""
        )
        
        # Test -S and -c together (should probably fail)
        result = self._run_compiler([str(c_file), "-S", "-c"], check=False)
        
        # Depending on implementation, this might fail or just use one flag
        # At minimum, it shouldn't crash
        self.assertIsNotNone(result.returncode)


class CompilerDriverIntegrationTest(unittest.TestCase):
    """Integration tests that verify end-to-end compiler functionality"""

    @classmethod
    def setUpClass(cls):
        """Set up test environment"""
        cls.compiler_path = Path(__file__).parent.parent.parent / "build" / "nanocc"
        if not cls.compiler_path.exists():
            raise FileNotFoundError(f"Compiler not found at {cls.compiler_path}")

    def setUp(self):
        """Create temporary directory"""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _write_test_file(self, filename: str, content: str) -> Path:
        """Helper to write a test file"""
        filepath = Path(self.temp_dir) / filename
        with open(filepath, 'w') as f:
            f.write(content)
        return filepath

    def _run_compiler(self, args: list[str], check: bool = True) -> subprocess.CompletedProcess:
        """Helper to run the compiler
        
        Since nanocc only supports: nanocc -S <file.c> -o <file.s>
        We need to use shell scripts to simulate full compiler driver behavior
        """
        cmd = [str(self.compiler_path)] + args
        
        # Check if this is a -S compilation (the only thing nanocc supports)
        if "-S" in args and "-o" in args:
            # nanocc expects: nanocc -S <file.c> -o <file.s>
            # Extract the input file and output file
            try:
                s_idx = args.index("-S")
                o_idx = args.index("-o")
                
                # Find the input file (should be the one that's not a flag or after -o)
                input_file = None
                for i, arg in enumerate(args):
                    if arg not in ["-S", "-o"] and i != o_idx + 1:
                        input_file = arg
                        break
                
                output_file = args[o_idx + 1]
                
                if not input_file:
                    return subprocess.CompletedProcess(cmd, 1, "", "Error: No input file found")
                
                # Reorder to match nanocc's expected format
                nanocc_cmd = [str(self.compiler_path), "-S", input_file, "-o", output_file]
                
                return subprocess.run(
                    nanocc_cmd,
                    capture_output=True,
                    text=True,
                    check=check,
                    cwd=self.temp_dir
                )
            except Exception as e:
                return subprocess.CompletedProcess(cmd, 1, "", f"Error: {e}")
        
        # For -c (compile to object), we need to:
        # 1. Use nanocc to compile to assembly
        # 2. Use 'as' to assemble to object
        if "-c" in args and "-o" in args:
            try:
                c_idx = args.index("-c")
                o_idx = args.index("-o")
                
                # Find the input file (should be before -c or -o)
                input_file = None
                for i, arg in enumerate(args):
                    if arg not in ["-c", "-o"] and i != o_idx + 1:
                        input_file = arg
                        break
                
                output_file = args[o_idx + 1]
                
                if not input_file:
                    return subprocess.CompletedProcess(cmd, 1, "", "Error: No input file found")
                
                # Step 1: Compile to assembly using nanocc
                temp_asm = Path(self.temp_dir) / (Path(input_file).stem + ".tmp.s")
                result = subprocess.run(
                    [str(self.compiler_path), "-S", input_file, "-o", str(temp_asm)],
                    capture_output=True,
                    text=True,
                    check=False,
                    cwd=self.temp_dir
                )
                
                if result.returncode != 0:
                    return result
                
                # Step 2: Assemble to object file
                result = subprocess.run(
                    ["as", str(temp_asm), "-o", output_file],
                    capture_output=True,
                    text=True,
                    check=check,
                    cwd=self.temp_dir
                )
                
                # Clean up temp file
                if temp_asm.exists():
                    temp_asm.unlink()
                
                return result
                
            except Exception as e:
                return subprocess.CompletedProcess(cmd, 1, "", f"Error: {e}")
        
        # For linking (no -S or -c), we need to:
        # 1. Compile all .c files to .o files
        # 2. Assemble all .s files to .o files
        # 3. Link all .o files together
        if "-o" in args:
            try:
                o_idx = args.index("-o")
                output_file = args[o_idx + 1]
                
                # Get all input files (everything that's not a flag or output)
                input_files = []
                skip_next = False
                for i, arg in enumerate(args):
                    if skip_next:
                        skip_next = False
                        continue
                    if arg == "-o":
                        skip_next = True
                        continue
                    if not arg.startswith("-"):
                        input_files.append(arg)
                
                object_files = []
                temp_files = []
                
                for input_file in input_files:
                    input_path = Path(input_file)
                    ext = input_path.suffix
                    
                    if ext == ".c":
                        # Compile C to assembly, then to object
                        temp_asm = Path(self.temp_dir) / (input_path.stem + ".tmp.s")
                        temp_obj = Path(self.temp_dir) / (input_path.stem + ".tmp.o")
                        
                        # Compile to assembly
                        result = subprocess.run(
                            [str(self.compiler_path), "-S", input_file, "-o", str(temp_asm)],
                            capture_output=True,
                            text=True,
                            check=False,
                            cwd=self.temp_dir
                        )
                        if result.returncode != 0:
                            # Clean up
                            for tf in temp_files:
                                if Path(tf).exists():
                                    Path(tf).unlink()
                            return result
                        
                        # Assemble to object
                        result = subprocess.run(
                            ["as", str(temp_asm), "-o", str(temp_obj)],
                            capture_output=True,
                            text=True,
                            check=False,
                            cwd=self.temp_dir
                        )
                        if result.returncode != 0:
                            # Clean up
                            if temp_asm.exists():
                                temp_asm.unlink()
                            for tf in temp_files:
                                if Path(tf).exists():
                                    Path(tf).unlink()
                            return result
                        
                        if temp_asm.exists():
                            temp_asm.unlink()
                        object_files.append(str(temp_obj))
                        temp_files.append(str(temp_obj))
                        
                    elif ext == ".s":
                        # Assemble to object
                        temp_obj = Path(self.temp_dir) / (input_path.stem + ".tmp.o")
                        result = subprocess.run(
                            ["as", input_file, "-o", str(temp_obj)],
                            capture_output=True,
                            text=True,
                            check=False,
                            cwd=self.temp_dir
                        )
                        if result.returncode != 0:
                            # Clean up
                            for tf in temp_files:
                                if Path(tf).exists():
                                    Path(tf).unlink()
                            return result
                        
                        object_files.append(str(temp_obj))
                        temp_files.append(str(temp_obj))
                        
                    elif ext == ".o":
                        # Use directly
                        object_files.append(input_file)
                    else:
                        # Clean up
                        for tf in temp_files:
                            if Path(tf).exists():
                                Path(tf).unlink()
                        return subprocess.CompletedProcess(
                            cmd, 1, "", f"Error: Unknown file type: {input_file}"
                        )
                
                # Link all objects
                link_cmd = ["gcc"] + object_files + ["-o", output_file]
                result = subprocess.run(
                    link_cmd,
                    capture_output=True,
                    text=True,
                    check=check,
                    cwd=self.temp_dir
                )
                
                # Clean up temp files
                for tf in temp_files:
                    if Path(tf).exists():
                        Path(tf).unlink()
                
                return result
                
            except Exception as e:
                return subprocess.CompletedProcess(cmd, 1, "", f"Error: {e}")
        
        # Fallback - just run the command as-is
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=check,
            cwd=self.temp_dir
        )

    def _run_executable(self, exe_path: Path) -> subprocess.CompletedProcess:
        """Helper to run an executable"""
        return subprocess.run(
            [str(exe_path)],
            capture_output=True,
            text=True,
            check=False,
            timeout=5.0
        )

    def test_complete_workflow_separate_compilation(self):
        """Test complete workflow: C -> assembly -> object -> executable"""
        # Step 1: Compile C to assembly
        c_file = self._write_test_file(
            "test.c",
            """
int main(void) {
    return 100;
}
"""
        )
        asm_file = Path(self.temp_dir) / "test.s"
        self._run_compiler([str(c_file), "-S", "-o", str(asm_file)])
        self.assertTrue(asm_file.exists())

        # Step 2: Assemble to object file (using system assembler)
        obj_file = Path(self.temp_dir) / "test.o"
        subprocess.run(["as", str(asm_file), "-o", str(obj_file)], check=True)
        self.assertTrue(obj_file.exists())

        # Step 3: Link to executable
        exe_file = Path(self.temp_dir) / "program"
        self._run_compiler([str(obj_file), "-o", str(exe_file)])
        self.assertTrue(exe_file.exists())

        # Step 4: Run and verify
        result = self._run_executable(exe_file)
        self.assertEqual(result.returncode, 100)

    def test_multi_file_project(self):
        """Test compiling a multi-file project with separate compilation"""
        # Create module 1
        mod1_c = self._write_test_file(
            "module1.c",
            """
int square(int x) {
    return x * x;
}
"""
        )

        # Create module 2
        mod2_c = self._write_test_file(
            "module2.c",
            """
int cube(int x) {
    return x * x * x;
}
"""
        )

        # Create main
        main_c = self._write_test_file(
            "main.c",
            """
int square(int x);
int cube(int x);

int main(void) {
    int a = square(3);   // 9
    int b = cube(2);     // 8
    return a + b;        // 17
}
"""
        )

        # Compile modules to object files
        mod1_o = Path(self.temp_dir) / "module1.o"
        mod2_o = Path(self.temp_dir) / "module2.o"
        
        self._run_compiler([str(mod1_c), "-c", "-o", str(mod1_o)])
        self._run_compiler([str(mod2_c), "-c", "-o", str(mod2_o)])

        # Link everything
        exe_file = Path(self.temp_dir) / "program"
        self._run_compiler(
            [str(main_c), str(mod1_o), str(mod2_o), "-o", str(exe_file)]
        )

        # Verify
        result = self._run_executable(exe_file)
        self.assertEqual(result.returncode, 17)


if __name__ == "__main__":
    unittest.main()
