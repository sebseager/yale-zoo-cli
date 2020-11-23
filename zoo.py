#!/usr/bin/python

import sys
import os
from argparse import ArgumentParser
from subprocess import Popen, PIPE

# globals
is_py3 = sys.version_info > (3, 0)
config_file = os.path.expanduser('~/.zoo_config')
config_data = {}
classes_dir = '/home/classes/'


def read_config():
    if not os.path.isfile(config_file):
        print("Run 'zoo config net_id class_label' first to set up configuration files.")
        sys.exit(0)

    with open(config_file, 'r') as f:
        for line in f:
            ln = [n.strip() for n in line.split(':')]
            config_data[ln[0]] = ln[1]


def write_config(net_id, class_label):
    ssh_config_path = '~/.ssh/config'
    ssh_config_path_full = os.path.expanduser(ssh_config_path)
    ssh_identity = "Host zoo\n\tHostName node.zoo.cs.yale.edu\n\tUser %s\n\tPort 22" % net_id
    create_str = "No SSH configuration file exists at %s. Create a new one [y|n]? "
    confirm_str = "\n%s\n\nAppend the above entry to file at %s [y|n]? " % (ssh_identity, ssh_config_path)

    # default configuration
    cfg = {'net_id': net_id, 'class_label': class_label, 'autograde_cmd': 'autograde --test'}
    with open(config_file, 'w') as f:
        f.write('\n'.join(('%s:%s' % (k, v) for k, v in cfg.items())))

    if not os.path.isfile(ssh_config_path_full):
        create_ok = str(input(create_str) if is_py3 else raw_input(create_str))
        if create_ok.lower != 'y':
            print("Exiting.")
            return

    with open(ssh_config_path_full, 'r+') as f:
        if ssh_identity in f.read():
            print("SSH configuration file at %s already contains Zoo entry." % ssh_config_path_full)
            return
        # this is ok since file pointer is now at end after f.read()
        append_ok = str(input(confirm_str) if is_py3 else raw_input(confirm_str))
        if append_ok.lower() != 'y':
            print("Exiting.")
            return
        f.writelines(('\n', ssh_identity, '\n'))


def upload(hw_num, local_file, zoo_dest, prob_nums, is_verbose, do_submit):
    send('scp %s zoo:%s' % (local_file, zoo_dest), ssh=False)
    class_bins = os.path.join(classes_dir, config_data['class_label'], 'bin/')
    correct_text, wrong_text = 'Your output is CORRECT', 'Your output is WRONG'

    if prob_nums is not None:
        ag_cmds = ('&& %s/%s %s %s' % (class_bins, config_data['autograde_cmd'], hw_num, p) for p in prob_nums)
        ag_out = send('cd %s %s' % (zoo_dest, ' '.join(ag_cmds)))
        output_str = "homework %s problems %s" % (hw_num, ', '.join(str(n) for n in prob_nums))
        if is_verbose:
            print("Autograde output for %s" % output_str)
            print(ag_out)
        ag_list = ag_out.split('\n')
        num_correct = sum((1 for n in ag_list if correct_text in n))
        num_wrong = sum((1 for n in ag_list if wrong_text in n))
        print("Autograde summary for %s" % output_str)
        print("%s correct and %s wrong, out of %s total" % (num_correct, num_wrong, num_correct + num_wrong))

        if num_wrong > 0:
            ag_len = len(ag_list)
            ag_splits = [0] + [i + 1 for i, v in enumerate(ag_list) if '====' in v and 'Problem' in v]
            probs = [ag_list[i:j] for i, j in zip(ag_splits, ag_splits + ([ag_len] if ag_list[-1] != ag_len else []))]
            print("Details for wrong answers\n")
            for prob in probs:
                if any((wrong_text in n for n in prob)):
                    print('\n'.join(prob), '\n')

    if do_submit:
        zoo_file = os.path.basename(local_file)
        if prob_nums is not None:
            try:
                if num_wrong > 0:
                    submit_ok = input("Autograde reported %s wrong responses. Go ahead with submit [y|n]?" % num_wrong)
                    if submit_ok.lower() != 'y':
                        return
            except NameError:
                submit_ok = input("Something went wrong with autograde. Go ahead with submit [y|n]?")
                if submit_ok.lower() != 'y':
                    return
            cmd = 'cd %s && %s/submit %s %s && check %s' % (zoo_dest, class_bins, hw_num, zoo_file, hw_num)
            submit_out = send(cmd)
            print(submit_out)


def download(zoo_path, local_dest, is_zoo_path_relative):
    path = os.path.join(classes_dir, config_data['class_label'], zoo_path) if is_zoo_path_relative else zoo_path
    send('scp zoo:%s %s' % (path, local_dest), ssh=False)


def send(cmd, ssh=True):
    session = ['ssh', 'zoo', 'bash'] if ssh else ['bash']
    proc = Popen(session, stdin=PIPE, stdout=PIPE)
    out, err = proc.communicate(cmd.encode('utf-8'))
    return out.decode('utf-8')


if __name__ == '__main__':
    parser = ArgumentParser(description="Client-side wrapper for Yale CPSC's Zoo submit system.")
    subparsers = parser.add_subparsers(dest='command')
    config_parser = subparsers.add_parser('config')
    config_parser.add_argument('net_id')
    config_parser.add_argument('class_label', help="e.g., 'cs201'")
    up_parser = subparsers.add_parser('up')
    up_parser.add_argument('hw_num', help='Homework assignment number', type=int)
    up_parser.add_argument('local_file', help='Path to source file to upload to Zoo')
    up_parser.add_argument('zoo_dest', help='Path to destination directory on the Zoo')
    up_parser.add_argument('--test', dest='prob_nums', nargs='*', type=int,
                           help='Runs Zoo autograde tests on all specified problem numbers (e.g. --test 1 2 4)')
    up_parser.add_argument('-v', action='store_true', help='Display full Zoo outputs')
    up_parser.add_argument('--submit', action='store_true', help='Submit the uploaded assignment')
    dn_parser = subparsers.add_parser('dn')
    dn_parser.add_argument('zoo_path', help='Path to source file on the Zoo')
    dn_parser.add_argument('local_dest', help='Path to local destination directory')
    dn_parser.add_argument('-c', action='store_true',
                           help="Interpret zoo_path as relative to your class' directory in /home/classes/")

    args = parser.parse_args()

    if args.command == 'config':
        write_config(args.net_id, args.class_label)

    read_config()

    if args.command == 'up':
        upload(args.hw_num, args.local_file, args.zoo_dest, args.prob_nums, args.v, args.submit)
    elif args.command == 'dn':
        download(args.zoo_path, args.local_dest, args.c)
