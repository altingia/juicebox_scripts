#!usr/bin/python
'''
Shawn Sullivan
October 31, 2018
Phase Genomics

juicebox_scripts/test_juicebox_assembly_converter.py

This file contains unit tests for functions of the
juicebox_assembly_converter.py script.

Copyright 2018, Phase Genomics Inc. All rights reserved.

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as
published by the Free Software Foundation, either version 3 of the
License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see https://www.gnu.org/licenses/agpl-3.0.en.html
'''
from __future__ import print_function

import sys
import functools
from _collections import defaultdict

class ContigNotFoundError(ValueError):
    pass


class JuiceboxConverter:
    '''The JuiceboxConverter class offers methods to read in a Juicebox
    .assembly file and the accompanying .fasta file, and generates a
    flexible data structure (ProcessedAssembly) which can be used to
    output additional file formats. Via the contig_mode flag, it
    supports simply reading in a .assembly file and reflecting the
    scaffold structures present in that file, as well as reading in the
    .assembly file and only outputting the contigs it describes, which
    is useful when only desiring contigs which have been broken using
    Juicebox.
    
    Attributes:
        None
    '''
    def __init__(self):
        pass
    
    def process(self, fasta, assembly, contig_mode=False, verbose=False,
                simple_chr_names=False):
        '''Read in a .assembly file and .fasta file, generating a
        ProcessedAssembly reflecting them.
        
        Args:
            fasta (str): path to the fasta corresponding to the assembly
            assembly (str): path to the .assembly file generated by
                Juicebox containing the results of using it
            contig_mode (bool) [optional]: instead of generating a
                ProcessedAssembly reflecting the scaffolds in the bottom
                portion of the .assembly file, only reflect the contigs
                described in the top portion of the file. Useful when
                you have broken contigs in Juicebox and only want to get
                an assembly reflecting those breaks, without
                scaffolding. Default: False
            simple_chr_names (bool): whether to use simple chromosome
                names ("ChromosomeX") for scaffolds instead of detailed
                chromosome names ("PGA_scaffold_X__Y_contigs__length_Z").
                Has no effect in contig_mode.
            verbose (bool) [optional]: print output describing processing
                steps to stdout. Otherwise silent. Default: False
        
        Returns:
            ProcessedAssembly: a ProcessedAssembly object reflecting the
                inputs
        '''
        if verbose:
            print('Reading sequences from {0}...'.format(fasta))
        sequences = self._read_fasta(fasta, verbose=verbose)
        if verbose:
            print('Sequences read\n')
            print('Reading .assembly file {0}...'.format(assembly))
        assembly_map, scaffolds = self._read_assembly(assembly, contig_mode=contig_mode)
        if verbose:
            print('.assembly read\n')
            print('Checking for breaks listed in .assembly and making them...')
        sequences = self._add_breaks(sequences, assembly_map)
        if verbose:
            print('Break check complete\n')
        return ProcessedAssembly(sequences, assembly_map, scaffolds, simple_chr_names=simple_chr_names)
    
    def _read_fasta(self, fasta, verbose=False):
        '''Read in a .fasta file and return a dictionary mapping the
        sequence names to their sequences.
        
        Args:
            fasta (str): path to the fasta containing the sequences you
                wish to read
            verbose (bool) [optional]: print output describing processing
                steps to stdout. Otherwise silent. Default: False
        
        Returns:
            dict[str:str]: dict mapping contig/sequence names present in
                the .fasta to their sequences
        '''
        sequences = dict()
        active_seq = None
        read_count = 0
        last_seq = None
        seq_list = list()
        dots_on_line = 0
        with open(fasta) as f:
            for line in f:
                line = line.strip()
                if len(line) == 0:
                    continue
                if verbose and read_count % 1000000 == 0:
                    if dots_on_line == 40 and read_count > 0:
                        print('')
                        dots_on_line = 0
                    print('.', end='')
                    dots_on_line += 1
                    sys.stdout.flush()
                read_count += 1
                if line[0] == '>':
                    if active_seq is not None:
                        sequences[active_seq] = ''.join(seq_list)
                        seq_list = list()
                    active_seq = line[1:].split()[0]
                    if active_seq in sequences.keys():
                        raise InvalidFastaError('Fasta {0} contains multiple contigs named {1}'.format(fasta, active_seq))
                    sequences[active_seq] = ''
                elif active_seq is not None:
                    seq_list.append(line)
                else:
                     raise InvalidFastaError('Fasta {0} does not begin with a contig name'.format(fasta))
        sequences[active_seq] = ''.join(seq_list)
        if verbose and read_count % 200000 != 0 and read_count > 0:
            print('')
        return sequences
    
    def _read_assembly(self, assembly, contig_mode=False):
        '''Read in a .assembly file and return two lists reflecting its
        contents, one for the contig list in the top of the file and the
        other the scaffolds listed at the bottom of the file.
        
        Args:
            assembly (str): path to the Juicebox .assembly file to
                process
            contig_mode (bool): whether to process the assembly in a
                manner which reflects the scaffolds in the bottom of the
                file, or just lists the contigs without scaffolding in
                the scaffold list. Default: False
        
        Returns:
            (list, list): tuple of two lists reflecting the .assembly
                file
                list[(str, str), (str, str), ...]: information about the
                    contigs shown in the top section of the file. The
                    list includes a tuple for each contig listed in the
                    .assembly file, in the order they are listed in the
                    top section of the assembly file.
                    str: the contig name
                    str: the contig length
                list[list[(str, str, str, bool), (str, str, str, bool), ...]:
                    information about the scaffolds shown in the bottom
                    section of the file, or about the contigs in the top
                    section of the file if contig_mode is True. Each
                    individual scaffold is a list containing the contigs
                    on that scaffold. Ordering within these lists matches
                    the ordering of contigs shown in the scaffolds
                    section at the bottom of the .assembly file if
                    contig_mode is False. If contig_mode is True, each
                    scaffold only contains a single contig, and they
                    are ordered in the same order they are present
                    in the top section of the .assembly file.
                    str: the contig name
                    str: the contig length
                    str: the contig strand (+ or -)
                    bool: whether the contig was placed using contig_mode
                        or not
        '''
            
        assembly_map = list()
        scaffolds = list()
        unscaffolded_contigs = list()
        with open(assembly) as f:
            for line in f:
                line = line.strip()
                if len(line) == 0:
                    continue
                if line[0] == '>':
                    # >cname index len
                    tokens = line[1:].split()
                    if int(tokens[1]) != len(assembly_map) + 1:
                        raise MissingFragmentError('Assembly {0} is missing the sequence for index {1}'.format(assembly, len(assembly_map) + 1))
                    if int(tokens[2]) == 0:
                        raise ZeroLengthContigError('Assembly {0} lists contig {1} as zero length'.format(assembly, tokens[0]))
                    assembly_map.append((tokens[0], str(int(tokens[2]) - 1)))
                    unscaffolded_contigs.append(tokens[0])
                else:
                    if contig_mode:
                        for contig in assembly_map:
                            scaffolds.append([(contig[0], contig[1], '+', contig_mode)])
                            unscaffolded_contigs.remove(contig[0])
                        break
                    else:
                        scaffold = list()
                        contigs = line.split()
                        for contig in contigs:
                            index = abs(int(contig)) - 1
                            strand = '+' if int(contig) > 0 else '-'
                            scaffold.append((assembly_map[index][0], assembly_map[index][1], strand, contig_mode))
                            unscaffolded_contigs.remove(assembly_map[index][0])
                        scaffolds.append(scaffold)
        if len(unscaffolded_contigs) != 0:
            raise UnscaffoldedContigError('Contigs are not included in scaffolding output: {0}'.format(unscaffolded_contigs))
        if contig_mode:
            scaffolds.sort()
        return assembly_map, scaffolds
    
    def _add_breaks(self, sequences, assembly_map):
        '''Introduce breaks into an assembly_map, as generated by
        _read_assembly, where indicated in the .assembly file. Does not
        mutate sequences - instead it returns a brand new sequences
        dict.
        
        Args:
            sequences (dict[str:str]): dictionary mapping contig/sequence
                names to their sequences
            assembly_map (list[(str, str)]: list containing contig
                information from the .assembly file, as generated by
                _read_assembly
        
        Returns:
            dict[str:str]: a brand new dictionary mapping contig/
                sequence names to their sequences, after performing
                breaks suggested by the contig names and information in
                assembly_map
        '''
        sequence_offsets = defaultdict(int)
        new_sequences = dict()
        orig_sequences = sequences.keys()
        # processing fragments in order is a problem as contigs will not necessarily be in order of fragments!!
        # e.g. it is possible to get fragment_3, fragment_1, fragment_2 as input order, leading to slicing errors.
        num_frags = 0
        assembly_map.sort(key=functools.cmp_to_key(cmp_assembly_map_entries))
        for fragment in assembly_map:
            #print(fragment)
            num_frags += 1
            if num_frags % 100 == 0:
                print(num_frags, "contigs processed for breaks")
            fragment_name = fragment[0]
            fragment_size = int(fragment[1])
            if (':::fragment' in fragment_name or '___fragment' in fragment_name) and fragment_name not in orig_sequences:
                if ':::fragment' in fragment_name:
                    orig_contig = ':::fragment'.join(fragment_name.split(':::fragment')[:-1])
                else:
                    orig_contig = '___fragment'.join(fragment_name.split('___fragment')[:-1])
                if orig_contig not in sequences:
                    orig_contig = fragment_name.replace(':::', '___')
                if orig_contig not in sequences:
                    raise ContigNotFoundError('Could not find contig {0} in original FASTA'.format(fragment))
                #print(orig_contig)
                new_sequences[fragment_name] = sequences[orig_contig][sequence_offsets[orig_contig]:sequence_offsets[orig_contig]+fragment_size]
                sequence_offsets[orig_contig] += fragment_size
                if fragment_size != len(new_sequences[fragment_name]):
                    print("original contig {3} is {0} and fragment {4} length is {1}".format(
                        fragment_size, len(new_sequences[fragment_name]), orig_contig, fragment_name))
            else:
                new_sequences[fragment_name] = sequences[fragment_name]
        return new_sequences

def cmp_assembly_map_entries(frag1, frag2):
    '''Sort comparison fn to allow us to reorder fragments of broken contigs according to position in original contig.
    Allows us to process assemblies regardless of input order.

    Args:
        frag1 ((str, str)): entry from assembly_maps
        frag2 ((str, str)): entry from assembly_maps

    Returns:
        int: the cmp order of the two fragments (-1, 0, or 1)

    '''
    names1 = extract_contig_info(frag1[0])
    names2 = extract_contig_info(frag2[0])
    # order doesn't matter if not from same orig contig
    if names1["orig"] != names2["orig"]:
        if names1["orig"] > names2["orig"]:
            return 1
        elif names1["orig"] < names2["orig"]:
            return -1
        else:
            raise BadContigNameError("contig {0} or {1} wrong??".format(
                                     frag1[0], frag2[0]))
    # else have to infer relative ordering of frags from same contig
    else:
        if names1["index"] is None or names1["index"] is None:
            raise BadContigNameError("contig {0} or {1} is formatted as if broken but no fragment detected??".format(
                                     frag1[0], frag2[0]))
        if names1["index"] > names2["index"]:
            order = 1
        elif names1["index"] < names2["index"]:
            order = -1
        else:
            raise BadContigNameError("contigs {0} and {1} repeated??".format(frag1[0], frag2[0]))
    return order

def extract_contig_info(name):
    '''Assuming Juicebox contig breaking convention (":::fragment_n:::debris"), extract original contig name and
    fragment index of a given contig (unbroken contigs are'''
    names = {}
    frag_fields = name.split(":::")
    if len(frag_fields) == 1:
        names["orig"] = frag_fields[0]
        names["index"] = None
    else:
        if frag_fields[-1] == "debris":
            frag_fields.pop()
        names["orig"] = ":::".join(frag_fields[:-1])
        names["index"] = int(frag_fields[-1].replace("fragment_", ""))
    return names


class ProcessedAssembly:
    '''The ProcessedAssembly class represents the results of
    JuiceboxConverter parsing a .fasta file and a .assembly file. It
    provides methods to output those processed results in several formats
    (.fasta, .agp, .bed) and also can generate a report describing any
    breaks that were introduced into the assembly by the .assembly file.
    
    Attributes:
        sequences (dict[str:str]): dictionary mapping contig names to
            their sequences
        assembly_map (list[(str, str)]: list containing contig
            information from the .assembly file, as generated by
            JuiceboxConverter._read_assembly
        scaffolds (list[list[(str, str, str, bool)): list containing
            scaffold information from the .assembly file, as generated by
            JuiceboxConverter._read_assembly
        simple_chr_names (bool): whether to use simple chromosome names
            ("ChromosomeX") for scaffolds instead of detailed chromosome
            names ("PGA_scaffold_X__Y_contigs__length_Z"). Has no effect
            in contig_mode.
    '''
    def __init__(self, sequences, assembly_map, scaffolds,
                 simple_chr_names=False):
        self.sequences = sequences
        self.assembly_map = assembly_map
        self.scaffolds = scaffolds
        self.contig_mode = scaffolds[0][0][3]
        self.simple_chr_names = simple_chr_names
        self.gap_size = 100
        self.complements = {
                                'A' : 'T',
                                'C' : 'G',
                                'G' : 'C',
                                'T' : 'A',
                                'a' : 't',
                                'c' : 'g',
                                'g' : 'c',
                                't' : 'a',
                                'N' : 'N',
                                'n' : 'n'
                            }
    
    def write_fasta(self, outfile, verbose=False):
        '''Write FASTA output to a specified file
        
        Args:
            outfile (str): path to the file to write to
            verbose (bool) [optional]: print output describing processing
                steps to stdout. Otherwise silent. Default: False
        '''
        if verbose:
            print('Writing FASTA to {0}...'.format(outfile))
            sys.stdout.flush()
        self._write_file(outfile, self.fasta(verbose=verbose), verbose=verbose)
    
    def write_agp(self, outfile, verbose=False):
        '''Write AGP output to a specified file
        
        Args:
            outfile (str): path to the file to write to
            verbose (bool) [optional]: print output describing processing
                steps to stdout. Otherwise silent. Default: False
        '''
        if verbose:
            print('Writing AGP to {0}...'.format(outfile))
            sys.stdout.flush()
        self._write_file(outfile, self.agp(), verbose=verbose)
    
    def write_bed(self, outfile, verbose=False):
        '''Write BED output to a specified file
        
        Args:
            outfile (str): path to the file to write to
            verbose (bool) [optional]: print output describing processing
                steps to stdout. Otherwise silent. Default: False
        '''
        if verbose:
            print('Writing BED to {0}...'.format(outfile))
            sys.stdout.flush()
        self._write_file(outfile, self.bed(), verbose=verbose)
    
    def write_break_report(self, outfile, verbose=False):
        '''Write a report about breaks shown in the .assembly file to a
        specified file
        
        Args:
            outfile (str): path to the file to write to
            verbose (bool) [optional]: print output describing processing
                steps to stdout. Otherwise silent. Default: False
        '''
        if verbose:
            print('Writing break report to {0}...'.format(outfile))
            sys.stdout.flush()
        self._write_file(outfile, self.break_report(), verbose=verbose)
    
    def fasta(self, verbose=False):
        '''Generate a FASTA format representation of the
        ProcessedAssembly
        
        Returns:
            list[str]: list of strings representing the ProcessedAssembly
                in FASTA format
            verbose (bool) [optional]: print output describing processing
                steps to stdout. Otherwise silent. Default: False
        '''
        ret = list()
        contig_counter = 0
        contig_only_print_scalar = 100
        dots_on_line = 0
        for index, scaffold in enumerate(self.scaffolds):
            scaffold_name = self._make_scaffold_name(index+1, scaffold)
            ret.append('>' + scaffold_name + '\n')
            seq = ''
            for contig in scaffold:
                if verbose and contig_counter % (10 * (contig_only_print_scalar if len(scaffold) == 1 else 1)) == 0:
                    if dots_on_line == 40 and contig_counter > 0:
                        dots_on_line = 0
                        print('')
                    print('.', end='')
                    dots_on_line += 1
                    sys.stdout.flush()
                contig_counter += 1
                seq += self.sequences[contig[0]] if contig[2] == '+' else self._reverse_complement(self.sequences[contig[0]]) 
                if contig != scaffold[-1]:
                    seq += 'n' * self.gap_size
            ret += self._chunk_sequence(seq)
        ret[-1] = ret[-1].strip()
        if verbose and contig_counter % (10 * (contig_only_print_scalar if len(scaffold) == 1 else 1))  != 0 and contig_counter > 0:
            print('')
        return ret
    
    def agp(self):
        '''Generate an AGP format representation of the
        ProcessedAssembly
        
        Returns:
            list[str]: list of strings representing the ProcessedAssembly
                in AGP format
        '''
        ret = list()
        ret.append('##agp-version 2.0\n')
        ret.append('# This file was generated by converting juicebox assembly format\n')
        for index, scaffold in enumerate(self.scaffolds):
            scaffold_name = self._make_scaffold_name(index+1, scaffold)
            if not self.contig_mode:
                scaffold_name = scaffold_name.split()[0]
            offset_coord = 1
            part_number = 1
            for contig in scaffold:
                ret.append(self._make_agp_line(scaffold_name, contig, offset_coord, part_number))
                offset_coord += int(contig[1])
                part_number += 1
                if contig != scaffold[-1]:
                    ret.append(self._make_agp_gap_line(scaffold_name, offset_coord, part_number))
                    offset_coord += self.gap_size
                    part_number += 1
        ret[-1] = ret[-1].strip()
        return ret 
    
    def bed(self):
        '''Generate a BED format representation of the
        ProcessedAssembly
        
        Returns:
            list[str]: list of strings representing the ProcessedAssembly
                in BED format
        '''
        ret = list()
        ret.append('##bed file\n')
        ret.append('# This file was generated by converting juicebox assembly format\n')
        gap_number = 1
        for index, scaffold in enumerate(self.scaffolds):
            scaffold_name = self._make_scaffold_name(index+1, scaffold)
            if not self.contig_mode:
                scaffold_name = scaffold_name.split()[0]
            offset_coord = 0
            for contig in scaffold:
                ret.append(self._make_bed_line(scaffold_name, contig, offset_coord))
                offset_coord += int(contig[1])
                if contig != scaffold[-1]:
                    ret.append(self._make_bed_gap_line(scaffold_name, offset_coord, gap_number))
                    offset_coord += self.gap_size
                    gap_number += 1
        ret[-1] = ret[-1].strip()
        return ret
    
    def break_report(self):
        '''Generate a report about breaks shown in the .assembly file 
        
        Returns:
            list[str]: list of strings summarizing the breaks present in
                the ProcessedAssembly
        '''
        ret = list()
        break_count = 0
        broken_orig_contigs = set()
        break_offsets = defaultdict(int)
        for contig in self.assembly_map:
            fragment_name = contig[0]
            fragment_size = contig[1]
            if ':::fragment' in fragment_name:
                orig_contig = fragment_name.split(':::fragment')[0]
                break_start = break_offsets[orig_contig]
                break_end = break_start + int(fragment_size)
                line = '\t'.join([
                                    orig_contig,
                                    fragment_name,
                                    str(break_start),
                                    str(break_end),
                                    fragment_size
                                ])
                ret.append(line + '\n')
                if ':::debris' in fragment_name:
                    break_count += 1
                broken_orig_contigs.add(orig_contig)
                break_offsets[orig_contig] += int(fragment_size)
        ret.insert(0, '#orig_contig\tfragment\tbreak_start\tbreak_end\tfragment_len\n')
        ret.insert(0, '#{0} total breaks in {1} contigs\n'.format(break_count, len(broken_orig_contigs)))
        #ret[-1] = ret[-1].strip()
        return ret
    
    def _write_file(self, outfile, contents, verbose=False):
        '''Write contents to a specified file
        
        Args:
            outfile (str): path to the file to write to
            contents (list[str]): list of strings to write to a file
            verbose (bool) [optional]: print output describing processing
                steps to stdout. Otherwise silent. Default: False
        '''
        with open(outfile, 'w') as f:
            f.writelines(contents)
        if verbose:
            print('Writing complete\n')
    
    def _make_scaffold_name(self, index, scaffold):
        '''Construct a string that shows the proper name of a scaffold.
        If running in contig_mode, just use the name of the contig
        instead.
        
        Args:
            index (int): the index of the scaffold
            scaffold list[(str, str, str, bool)]: a list of tuples
                reflecting the scaffold. Each tuple conforms to the
                schema used in JuiceboxConverter._read_assembly
                str: the contig name
                str: the contig length
                str: the contig strand (+ or -)
                bool: whether the contig was placed using contig_mode
                    or not
        '''
        if self.contig_mode:
            scaffold_name = '{0}'.format(scaffold[0][0]).replace(":::", "___")
        elif self.simple_chr_names:
            if len(scaffold) > 1:
                scaffold_name = 'Chromosome{0}'.format(index)
            else:
                #use the contig name style in this mode
                scaffold_name = '{0}'.format(scaffold[0][0]).replace(":::", "___")
        else:
            contig_count = len(scaffold)
            scaffold_length = 0
            for contig in scaffold:
                scaffold_length += int(contig[1])
                if contig != scaffold[-1]:
                    scaffold_length += self.gap_size
            scaffold_name = 'PGA_scaffold_{0}__{1}_contigs__length_{2}'.format(index,
                                                                               contig_count,
                                                                               scaffold_length)
        return scaffold_name
    
    def _chunk_sequence(self, sequence, line_len=80):
        '''Process a long string representation of a sequence into a list
        of chunks that are line_len long (the last string may be shorter)
        
        Args:
            sequence (str): the sequence to chunk
            line_len (int) [optional]: the length of the lines to break
                the sequence into. The last line may be shorter as it
                will be the remainder after chunking the rest of the
                sequence. Default: 80
        
        Returns:
            list(str): a list of strings reflecting the input sequence
                broken into chunks
        '''
        chunked_sequence = list()
        len_added = 0
        while len(sequence) - len_added > line_len:
            chunked_sequence.append(sequence[len_added:len_added+line_len] + '\n')
            len_added += line_len
        if len(sequence) - len_added > 0: 
            chunked_sequence.append(sequence[len_added:] + '\n')
        return chunked_sequence

    def _make_agp_line(self, scaffold_name, contig, offset_coord, part_number):
        '''Make a line for an AGP file reflecting the positioning of a
        single contig.
        
        Args:
            scaffold_name (str): the name of the scaffold the contig is
                placed on
            contig ((str, str, str, bool)): tuple containing the name of
                the contig and its length as strings. Matches the
                representation of contigs in a scaffolds as
                generated by JuiceboxConverter._read_assembly
            offset_coord (int): the offset of the contig in the scaffold
            part_number (int): the part number of the contig in the
                scaffold
        
        Returns:
            str: an AGP-format line reflecting the contig and other
                inputs
        '''
        scaff_start_coord = str(offset_coord)
        scaff_end_coord = str(offset_coord + int(contig[1]) - 1)
        elt_type = 'W'
        contig_name = contig[0]
        contig_start_coord = '1'
        contig_end_coord = contig[1]
        strand = contig[2]
        line = '\t'.join([
                            scaffold_name,
                            scaff_start_coord,
                            scaff_end_coord,
                            str(part_number),
                            elt_type,
                            contig_name,
                            contig_start_coord,
                            contig_end_coord,
                            strand
                        ])
        return line + '\n'
    
    def _make_agp_gap_line(self, scaffold_name, offset_coord, part_number):
        '''Make a line for an AGP file reflecting the positioning of a
        gap in the scaffold.
        
        Args:
            scaffold_name (str): the name of the scaffold the gap is
                placed on
            offset_coord (int): the offset of the gap in the scaffold
            part_number (int): the part number of the gap in the
                scaffold
        
        Returns:
            str: an AGP-format line reflecting the gap and other
                inputs
        '''
        gap_start_coord = str(offset_coord)
        gap_end_coord = str(offset_coord + self.gap_size - 1)
        elt_type = 'U'
        gap_size = str(self.gap_size)
        gap_type = 'scaffold'
        has_evidence = 'yes'
        evidence_type = 'paired-ends'
        line = '\t'.join([
                        scaffold_name,
                        gap_start_coord,
                        gap_end_coord,
                        str(part_number),
                        elt_type,
                        gap_size,
                        gap_type,
                        has_evidence,
                        evidence_type
                    ])
        return line + '\n'     
    
    def _make_bed_line(self, scaffold_name, contig, offset_coord):
        '''Make a line for a BED file reflecting the positioning of a
        single contig.
        
        Args:
            scaffold_name (str): the name of the scaffold the contig is
                placed on
            contig ((str, str, str, bool)): tuple containing the name of
                the contig and its length as strings. Matches the
                representation of contigs in a scaffolds as
                generated by JuiceboxConverter._read_assembly
            offset_coord (int): the offset of the contig in the scaffold
        
        Returns:
            str: a BED-format line reflecting the contig and other
                inputs
        '''
        start_coord = str(offset_coord)
        end_coord = str(offset_coord + int(contig[1]))
        contig_name = contig[0]
        contig_len = contig[1]
        strand = contig[2]
        line = '\t'.join([
                            scaffold_name,
                            start_coord,
                            end_coord,
                            contig_name,
                            contig_len,
                            strand
                        ])
        return line + '\n'
    
    def _make_bed_gap_line(self, scaffold_name, offset_coord, gap_number):
        '''Make a line for a BED file reflecting the positioning of a
        gap in the scaffold.
        
        Args:
            scaffold_name (str): the name of the scaffold the gap is
                placed on
            offset_coord (int): the offset of the gap in the scaffold
            gap_number (int): the index of the gap in the scaffold
        
        Returns:
            str: a BED-format line reflecting the gap and other
                inputs
        '''
        start_coord = str(offset_coord)
        end_coord = str(offset_coord + self.gap_size)
        gap_name = 'pg_gap_{0}'.format(gap_number)
        line = '\t'.join([
                            scaffold_name,
                            start_coord,
                            end_coord,
                            gap_name
                        ])
        return line + '\n'
    
    def _reverse_complement(self, sequence):
        '''Reverse complement a sequence
        
        Args:
            sequence (str): the sequence to reverse complement
        
        Returns:
            str: the reverse complement of the sequence
        '''
        return ''.join(self.complements[x] for x in reversed(sequence))
    


class ZeroLengthContigError(ValueError):
    '''An Error caused when a contig is listed as having zero length in
    a .assembly file'''
    pass

class UnscaffoldedContigError(ValueError):
    '''An Error caused when a contig is listed in a .assembly file, but
    is not placed anywhere in a scaffold.'''
    pass

class MissingFragmentError(ValueError):
    '''An Error caused when a contig or fragment is missing from the list
    of contigs at the start of the file'''
    pass

class InvalidFastaError(ValueError):
    '''An Error caused when an invalid .fasta file is attempted to be
    read.'''
    pass

class BadContigNameError(ValueError):
    '''An Error caused by a contig name that violates expected naming convention'''
    pass

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('-a', '--assembly', help='juicebox assembly file', required=True)
    parser.add_argument('-f', '--fasta', help='the fasta file', required=True)
    parser.add_argument('-p', '--prefix', help='the prefix to use for writing outputs. '\
                        'Default: the assembly file, minus the file extension', default=None)
    parser.add_argument('-c', '--contig_mode', action='store_true', help='ignore scaffold '\
                        'specification and just output contigs. useful when only trying to '\
                        'obtain a fasta reflecting juicebox breaks. Default: %(default)s',
                        default=False)
    parser.add_argument('-s', '--simple_chr_names', action='store_true', default=False,
                        help='use simple chromosome names ("ChromosomeX") for scaffolds '\
                        'instead of detailed chromosome names ("PGA_scaffold_X__Y_contigs__length_Z"). '\
                        'Has no effect in contig_mode.')
    parser.add_argument('-v', '--verbose', action='store_false', help='print summary of '\
                        'processing steps to stdout, otherwise silent. Default: %(default)s',
                        default=True)
    args = parser.parse_args()
    
    assembly = args.assembly
    fasta = args.fasta
    prefix = args.prefix
    if prefix is None:
        import os.path
        prefix = os.path.splitext(args.assembly)[0]
    contig_mode = args.contig_mode
    simple_chr_names = args.simple_chr_names
    verbose = args.verbose
    
    print('Processing assembly file. Details:')
    print('Assembly:\t\t\t{0}'.format(assembly))
    print('Fasta:\t\t\t\t{0}'.format(fasta))
    print('Output prefix:\t\t\t{0}'.format(prefix))
    print('Contig mode:\t\t\t{0}'.format(contig_mode))
    print('Simple Chromosome Names:\t{0}\n'.format(simple_chr_names))
    
    processed_assembly = JuiceboxConverter().process(fasta, assembly,
                                                     contig_mode=contig_mode,
                                                     verbose=verbose,
                                                     simple_chr_names=simple_chr_names)
    processed_assembly.write_agp(prefix + '.agp', verbose=verbose)
    processed_assembly.write_bed(prefix + '.bed', verbose=verbose)
    processed_assembly.write_break_report(prefix + '.break_report.txt', verbose=verbose)
    processed_assembly.write_fasta(prefix + '.fasta', verbose=verbose)

