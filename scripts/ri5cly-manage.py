#!/bin/python3


# Copyright 2016 ETH Zurich and University of Bologna.
# Copyright and related rights are licensed under the Solderpad Hardware
# License, Version 0.51 (the “License”); you may not use this file except in
# compliance with the License.  You may obtain a copy of the License at
# http://solderpad.org/licenses/SHL-0.51. Unless required by applicable law
# or agreed to in writing, software, hardware and materials distributed under
# this License is distributed on an “AS IS” BASIS, WITHOUT WARRANTIES OR
# CONDITIONS OF ANY KIND, either express or implied. See the License for the
# specific language governing permissions and limitations under the License.

################################################################################
## Engineer:       Markus Wegmann - markus.wegmann@technokrat.ch              ##
##                                                                            ##
## Project Name:   littleRISCV                                                ##
## Language:       Python 3.6                                                 ##
##                                                                            ##
## Description:    This program can overwrite the littleRISCV config and      ##
##                 export a clean version of the core. The macro switches     ##
##                 and all unnecessary code is removed in the root .sv files. ##
##                                                                            ##
################################################################################


import os
import shutil
import argparse
import re
import zipfile
import subprocess

def zipdir(path, ziph):
    # ziph is zipfile handle
    for root, dirs, files in os.walk(path):
        for file in files:
            ziph.write(os.path.relpath(os.path.join(root, file), os.path.join(path, '..')))


def main():
    littleRISCV_path = os.path.abspath(os.path.dirname(os.path.realpath(__file__)) + "/..")  # Path to littleRISCV folder
    print(littleRISCV_path)

    parser = argparse.ArgumentParser(description="Can overwrite config and export clean version of littleRISCV")
    parser.add_argument('-i', dest="new_riscv_config", metavar='.../new_riscv_config.sv',
                        help='path to a new config file to overwrite littleRISCV config')
    parser.add_argument('-o', dest='export_folder_path', metavar='.../export_folder_path',
                        help='path to a folder to export clean version of littleRISCV without preprocessor switches')
    parser.add_argument('-z', dest='zip', action='store_true',
                        help='zip the export into a tar.gz')
    parser.add_argument('--synthesize', dest='synthesize', action='store_true',
                        help='will synthesize the current or new configuration')
    parser.add_argument('--report', dest='report', action='store_true',
                        help='will report custom synthesized design')
    parser.add_argument('--synthesize_all', dest='synthesize_all', action='store_true',
                        help='will synthesize all sample configs in the scripts/example_configs folder with Synopsys')
    parser.add_argument('--report_all', dest='report_all', action='store_true',
                        help='will report all sample configs which have been synthesized')
    args = parser.parse_args()

    action_taken = False

    if args.new_riscv_config is not None:
        overwriteConfig(args.new_riscv_config, littleRISCV_path)
        action_taken = True

    if args.export_folder_path is not None:
        exportCleanVersion(args.export_folder_path, littleRISCV_path, zip=args.zip)
        action_taken = True

    if args.synthesize == True:
        synthesize(littleRISCV_path)
        action_taken = True

    if args.report == True:
        report(littleRISCV_path)
        action_taken = True

    if args.synthesize_all == True:
        reportAll(littleRISCV_path)
        action_taken = True
    elif args.report_all == True:
        synthesizeAll(littleRISCV_path)
        reportAll(littleRISCV_path)
        action_taken = True

    if action_taken == False:
        print("No action taken. Please see the help below for more information:")
        parser.print_help()


def overwriteConfig(new_config_path, littleRISCV_path):
    print("Overwriting current config (include/riscv_config.sv) with new one ({})".format(new_config_path))
    shutil.move(os.path.abspath(littleRISCV_path + "/include/riscv_config.sv"), os.path.abspath(littleRISCV_path + "/include/riscv_config.sv.bak")) # Backup
    shutil.copy(os.path.abspath(new_config_path), os.path.abspath(littleRISCV_path + "/include/riscv_config.sv")) # Copy new config to littleRISCV


def parseConfig(littleRISCV_path):
    print("Trying to parse configuration.")
    definitions = []
    config = os.path.abspath(littleRISCV_path + "/include/riscv_config.sv")

    with open(config, encoding="utf8") as f:
        nesting_counter = 0 # If we enter a not-enabled section, keep track when we leave the section again

        content = f.readlines()
        while len(content) > 0:
            line = content.pop(0)

            config_pattern = re.compile("^//.*CONFIG:\s(\w*)$") # Test for config declaration
            m = config_pattern.match(line)
            if m is not None and nesting_counter == 0:
                content.pop(0) # Pop description
                line = content.pop(0)

                config_value_pattern = re.compile("^`define\s(\w*)$") # Check if config enabled and extract name
                m = config_value_pattern.match(line)
                if m is not None:
                    definitions.append(m.group(1))
            else:
                ifdef_pattern = re.compile("^`ifdef\s(\w*)$") # Check if we have a dependant config
                m = ifdef_pattern.match(line)
                if m is not None:
                    if m.group(1) in definitions:
                        pass
                    else:
                        nesting_counter += 1

                ifndef_pattern = re.compile("^`ifndef\s(\w*)$") # Check if we have a dependant config
                m = ifndef_pattern.match(line)
                if m is not None:
                    if not (m.group(1) in definitions):
                        pass
                    else:
                        nesting_counter += 1

                endif_pattern = re.compile("^`endif.*$")  # Check if we ended a block
                m = endif_pattern.match(line)
                if m is not None:
                    nesting_counter -= 1
                    if nesting_counter < 0:
                        nesting_counter = 0

    print("Enabled CONFIG definitions: {}".format(definitions))
    return definitions


def processSystemVerilog(filename, folderpath, definitions):
    print("Processing: {}".format(filename))

    content = []
    new_content = []

    with open(os.path.abspath(folderpath+"/"+filename), encoding="utf8") as f:
        content = f.readlines()

    nesting_counter = 0  # If we enter a not-enabled section, keep track when we leave the section again
    is_else_true = False # at first occurence of missing declarations

    while len(content) > 0:
        is_codeline = True
        line = content.pop(0)

        config_pattern = re.compile("^\s*//.*CONFIG_REGION:\s(\w*)$")  # Test for config region declaration
        m = config_pattern.match(line)
        if m is not None:
            is_codeline = False
            line = content.pop(0)

            ifdef_pattern = re.compile("^\s*`ifdef\s(\w*)$")  # Check if we have an ifdef
            m = ifdef_pattern.match(line)
            if m is not None:
                if m.group(1) in definitions:
                    if nesting_counter == 0:
                        is_else_true = False
                    else:
                        nesting_counter += 1
                else:
                    if nesting_counter == 0:
                        is_else_true = True
                    nesting_counter += 1


            ifndef_pattern = re.compile("^\s*`ifndef\s(\w*)$")  # Check if we have an ifndef
            m = ifndef_pattern.match(line)
            if m is not None:
                if not (m.group(1) in definitions):
                    if nesting_counter == 0:
                        is_else_true = False
                    else:
                        nesting_counter += 1
                else:
                    if nesting_counter == 0:
                        is_else_true = True
                    nesting_counter += 1

        else_pattern = re.compile("^\s*`else.*$")  # Check if we have an else
        m = else_pattern.match(line)
        if m is not None:
            is_codeline = False
            if nesting_counter == 1 and is_else_true:
                nesting_counter -= 1
            if (not is_else_true) and nesting_counter == 0:
                nesting_counter += 1

        endif_pattern = re.compile("^\s*`endif.*$")  # Check if we have an endif
        m = endif_pattern.match(line)
        if m is not None:
            is_codeline = False
            nesting_counter -= 1
            if nesting_counter < 0:
                nesting_counter = 0

        if is_codeline and nesting_counter == 0:
            new_content.append(line)

    os.remove(os.path.abspath(folderpath+"/"+filename))

    with open(os.path.abspath(folderpath+"/"+filename), 'w', encoding="utf8") as f:
        f.writelines(new_content)


def exportCleanVersion(build_path, littleRISCV_path, zip=False):
    print("Exporting clean version of littleRISCV without preprocessor switches to defined output folder.")
    definitions = parseConfig(littleRISCV_path)

    shutil.rmtree(os.path.abspath(build_path), ignore_errors=True)
    shutil.copytree(os.path.abspath(littleRISCV_path), os.path.abspath(build_path), ignore=shutil.ignore_patterns("*.git", "scripts", "docs"))


    for filename in os.listdir(os.path.abspath(build_path)):
        sv_p = re.compile("^.*\.sv")
        m = sv_p.match(filename)
        if m is not None:
            processSystemVerilog(filename, build_path, definitions)

    with open(os.path.abspath(build_path+"/THIS_CORE_IS_AUTOMATICALLY_GENERATATED!!!.txt"), 'w', encoding="utf8") as f:
        f.write("This core export was automatically generated by ri5cly-manage.py\n\n")
        f.write("Following settings were enabled: {}".format(definitions))


    if zip is True:
        print("Zip exported version.")
        zipf = zipfile.ZipFile(os.path.abspath(build_path)+".zip", 'w', zipfile.ZIP_DEFLATED)
        zipdir(os.path.abspath(build_path), zipf)
        zipf.close()
        shutil.rmtree(os.path.abspath(build_path), ignore_errors=True)


def synthesizeAll(littleRISCV_path):
    if not os.path.exists(os.path.abspath(littleRISCV_path+"/../../../synopsys/start_synopsys_synth.py")):
        print("littleRISCV repository not contained in Imperio/Pulpino project! Canceling.")

    if not os.path.isdir(os.path.abspath(littleRISCV_path + "/scripts/synthesis_results/")):
        os.mkdir(os.path.abspath(littleRISCV_path + "/scripts/synthesis_results/"))

    for filename in os.listdir(os.path.abspath(littleRISCV_path + "/scripts/example_configs")):
        print("Synthesizing {}".format(filename))
        overwriteConfig(os.path.abspath(littleRISCV_path + "/scripts/example_configs/" + filename), littleRISCV_path)
        p = subprocess.Popen([os.path.abspath(littleRISCV_path+"/../../../synopsys/start_synopsys_synth.py")], cwd=os.path.abspath(littleRISCV_path+"/../../../synopsys/"))
        p.wait()

        shutil.copytree(os.path.abspath(littleRISCV_path + "/../../../synopsys"), os.path.abspath(littleRISCV_path + "/scripts/synthesis_results/" + filename))
        print("Synthesized {}".format(filename))

    print("Synthesized all configurations! Bye.")

def synthesize(littleRISCV_path):
    if not os.path.exists(os.path.abspath(littleRISCV_path+"/../../../synopsys/start_synopsys_synth.py")):
        print("littleRISCV repository not contained in Imperio/Pulpino project! Canceling.")

    if not os.path.isdir(os.path.abspath(littleRISCV_path + "/scripts/synthesis_results/")):
        os.mkdir(os.path.abspath(littleRISCV_path + "/scripts/synthesis_results/"))

    p = subprocess.Popen([os.path.abspath(littleRISCV_path+"/../../../synopsys/start_synopsys_synth.py")], cwd=os.path.abspath(littleRISCV_path+"/../../../synopsys/"))
    p.wait()

    shutil.copytree(os.path.abspath(littleRISCV_path + "/../../../synopsys"), os.path.abspath(littleRISCV_path + "/scripts/synthesis_results/custom"))

    print("Synthesized Imperio! Results are in little-riscv/scripts/synthesis_results/cusom. Bye.")

def report(littleRISCV_path):
    print("Config\t\tArea")

    area = os.system("cat " + os.path.abspath(littleRISCV_path + "/scripts/synthesis_results/custom/reports/imperio_*_area* | grep 'pulpino_i/core_region_i/RISCV_CORE' ")).read()
    area_pattern = re.compile("^pulpino_i/core_region_i/RISCV_CORE\s+(\d*)\s+.*$")
    m = area_pattern.match(area)
    area = m.group(1)
    area = float(area)
    area /= 1.44 * 1000.0

    print("{}\t\t\t\t\t\t\t{}".format("custom",area))

def reportAll(littleRISCV_path):
    print("Config\t\tArea")

    for filename in os.listdir(os.path.abspath(littleRISCV_path + "/scripts/example_configs")):
        area = os.system("cat " + os.path.abspath(littleRISCV_path + "/scripts/synthesis_results/" + filename + "/reports/imperio_*_area* | grep 'pulpino_i/core_region_i/RISCV_CORE' ")).read()
        area_pattern = re.compile("^pulpino_i/core_region_i/RISCV_CORE\s+(\d*)\s+.*$")
        m = area_pattern.match(area)
        area = m.group(1)
        area = float(area)
        area /= 1.44 * 1000.0

        print("{}\t\t\t\t\t\t\t{}".format(filename,area))




if __name__ == "__main__":
    main()