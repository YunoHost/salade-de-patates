# encoding: utf-8

import hmac
import hashlib
import requests

from datetime import datetime

from flask import Flask, request, abort
from pymongo import MongoClient

from common import get_by_id, get_none, get, generate_id
from github_to_wekan import import_pr, get_list_for_milestone, get_board, get_default_list


client = MongoClient()

# Card creation
# 
# {
#   text: '{{wekan-username}} added "{{card-title}}" to "{{list-name}}"\nhttp://{{wekan-host}}/b/{{board-id}}/{{board-name}}/{{card-id}}',
#   cardId: '{{card-id}}',
#   listId: '{{list-id}}',
#   boardId: '{{board-id}}',
#   user: '{{wekan-username}}',
#   card: '{{card-title}}',
#   description: 'act-createCard'
# }
# Card archival
# 
# {
#   text: '{{wekan-username}} archived "{{card-title}}"\nhttp://{{wekan-host}}/b/{{board-id}}/{{board-name}}/{{card-id}}',
#   cardId: '{{card-id}}',
#   listId: '{{list-id}}',
#   boardId: '{{board-id}}',
#   user: '{{wekan-username}}',
#   card: '{{card-title}}',
#   description: 'act-archivedCard'
# }
# Comment creation
# 
# {
#   text: '{{wekan-username}} commented on "{{card-title}}": "{{comment-body}}"\nhttp://{{wekan-host}}/b/{{board-id}}/{{board-name}}/{{card-id}}',
#   cardId: '{{card-id}}',
#   boardId: '{{board-id}}',
#   comment: '{{comment-body}}',
#   user: '{{wekan-username}}',
#   card: '{{card-title}}',
#   description: 'act-addComment'
# }
# Card move
# 
# {
#   text: '{{wekan-username}} moved "{{card-title}}" from "{{old-list-name}}" to "{{new-list-name}}"\nhttp://{{wekan-host}}/b/{{board-id}}/{{board-name}}/{{card-id}}',
#   cardId: '{{card-id}}',
#   listId: '{{new-list-id}}',
#   oldListId: '{{old-list-id}}',
#   boardId: '{{board-id}}',
#   user: '{{wekan-username}}',
#   card: '{{card-title}}',
#   description: 'act-moveCard'
# }

app = Flask(__name__)
token = open("wekan_webhook_token", "r").read().strip()

@app.route("/wekan/<secret>", methods=['POST'])
def wekan(secret):
    print request
    print request.json

    # sekuritay
    local_secret = open("./wekan_webhook_secret", "r").read().strip()

    if local_secret != secret.strip():
        abort(403)

    # TODO check that request is json and correct or some stuff like that

    # card create -> we don't care about it

    # if card not linked to github, we don't care about it

    # card archival
    # * does that mean that we close the PR?
    # * do we have unarchival event?

    # comment creation
    # * not yet supported

    # card move -> interesting part
    # TODO: mark "[MILESTONE]" or something like that in columns titles
    # * if card move in another milestone than its one -> change of milestone
    # * if card is moved out of milestone keep its milestone

    # we don't have card modification like title or description?

    # do we have milestone modifications events?
    # apparently no :(

    client = MongoClient()

    if request.json["description"] == "act-moveCard":
        card_id = request.json["cardId"]
        card = get_by_id(client.wekan.cards, card_id)

        pr_bridge = get_none(client.wekan.bridge_for_prs, {"wekan_id": card_id})

        print "bridge:", pr_bridge
        print "card:", card

        if pr_bridge is None:
            print "unhandled card", card_id
            return "unhandled card"

        project = pr_bridge["github_project"]

        list_id = request.json["listId"]

        list_ = get_none(client.wekan.bridge_for_milestones, {"wekan_id": list_id, "github_project": project})

        # list itself can't be none
        # list can be: know (a milestone), unknow
        # card was in a milestone, wasn't [back to its milestone or in another milestone]

        github_pr = requests.get("https://api.github.com/repos/yunohost/%s/pulls/%s" % (project, pr_bridge["github_id"])).json()

        github_milestone_id = github_pr["milestone"]["number"] if github_pr["milestone"] is not None else None

        if list_ is None:
            # try to detect if there is a list that is a milestone with
            # the same name but that isn't in that project, if so, create the
            # milestone in the project where it's missing

            list_bridge = list(client.wekan.bridge_for_milestones.find({"wekan_id": list_id}))

            if not list_bridge:
                print "new list is not known as a milestone, skip"
                return "ok"

            list_bridge = list_bridge[0]
            print "list is linked to milestone of other projects"
            print "-> create a milestone with the same name in '%s' project" % project

            # create the milestone on github on the project that hasn't have it
            list_ = get_by_id(client.wekan.lists, list_id)
            github_milestone = requests.post("https://api.github.com/repos/yunohost/%s/milestones" % project, json={"title": list_["title"].replace(" [MILESTONE]", "").strip()}, headers={"Authorization": "bearer %s" % token})
            print github_milestone
            print github_milestone.json()

            bridge_milestone_id = client.wekan.bridge_for_milestones.insert({
                "github_id": github_milestone.json()["number"],
                "github_project": project,
                "wekan_id": list_id
            })

            list_ = get_by_id(client.wekan.bridge_for_milestones, bridge_milestone_id)

        # check if target column milestone number != github_milestone_id
        # if so, change it
        # else return
        if list_["github_id"] != github_milestone_id:
            print "online github PR is different than the targeted list, change it"
            print requests.patch("https://api.github.com/repos/yunohost/%s/issues/%s" % (project, pr_bridge["github_id"]), json={"milestone": list_["github_id"]}, headers={"Authorization": "bearer %s" % token})

            query = open("./query-one.graphql", "r").read()
            pr = requests.post("https://api.github.com/graphql",
                               headers={"Authorization": "bearer %s" % token},
                               json={"query": query % (project, pr_bridge["github_id"])}).json()

            import_pr(client, project, pr["data"]["repository"]["pullRequest"])
        else:
            print "online github PR is the same than the targeted list, don't do anything"
            return "ok"

    return "ok"

@app.route("/github", methods=['POST'])
def github():
    # print request
    # print request.json

    # github_hook_secret = open("./secret_for_webhook", "r").read().strip()

    # > HMAC hex digest of the payload, using the hook's secret as the key (if
    # > configured)
    # if request.headers.get("X-Hub-Signature").strip() != github_hook_secret:
        # TODO real exception
        # raise 400


    # stolen and adapted from here
    # https://github.com/carlos-jenkins/python-github-webhooks/blob/d485b31c0291d06b5153198bc1de685d50731536/webhooks.py#L72-L93
    secret = open("./github_webhook_secret", "r").read().strip()

    # Only SHA1 is supported
    header_signature = request.headers.get('X-Hub-Signature')
    if header_signature is None:
        print "no header X-Hub-Signature"
        abort(403)

    sha_name, signature = header_signature.split('=')
    if sha_name != 'sha1':
        print "signing algo isn't sha1, it's '%s'" % sha_name
        abort(501)

    # HMAC requires the key to be bytes, but data is string
    mac = hmac.new(str(secret), msg=request.data, digestmod=hashlib.sha1)

    if not hmac.compare_digest(str(mac.hexdigest()), str(signature)):
        abort(403)

    hook_type = request.headers.get("X-Github-Event")

    print "Hook type:", hook_type

    if hook_type == "pull_request":
        token = open("graphql_token", "r").read().strip()
        query = open("./query-one.graphql", "r").read()

        project = request.json["repository"]["name"]
        number = request.json["pull_request"]["number"]

        pr = requests.post("https://api.github.com/graphql",
                           headers={"Authorization": "bearer %s" % token},
                           json={"query": query % (project, number)}).json()

        print "reimporting pr %s#%s" % (project, number)
        import_pr(client, project, pr["data"]["repository"]["pullRequest"])

    elif hook_type == "milestone":
        # actions: created, closed, opened, edited, deleted

        board = get_board(client)
        project = request.json["repository"]["name"]

        if request.json["action"] == "created":
            # I need to import it here

            # this is badly name but will create list (column) on the fly
            get_list_for_milestone(client, board, project, request.json["milestone"])

        elif request.json["action"] in ("closed", "deleted"):
            print "Milestone %s#%s as been closed on github" % (project, request.json["milestone"]["number"])
            bridge_milestone = get(client.wekan.bridge_for_milestones, {
                "github_id": request.json["milestone"]["number"],
                "github_project": project
            })

            # if all milestone pointing to this list are closed, archive to
            # column assuming the milestone exist
            print "checking if all other PR are closed"
            all_closed = True
            # get all milestone pointing to this list
            # this sucks because I need to contact github api
            for other_miletone in client.wekan.bridge_for_milestones.find({"wekan_id": bridge_milestone["wekan_id"]}):
                # GET /repos/:owner/:repo/milestones/:number
                other_project = other_miletone["github_project"]
                print "https://api.github.com/repos/yunohost/%s/milestones/%s" % (other_project, other_miletone["github_id"])
                other_miletone = requests.get("https://api.github.com/repos/yunohost/%s/milestones/%s" % (other_project, other_miletone["github_id"])).json()

                if other_miletone["state"] == "open":
                    print "milestone of '%s' is not closed (and maybe other), stop" % other_project
                    all_closed = False
                    break

            list_ = get_by_id(client.wekan.lists, bridge_milestone["wekan_id"])

            list_is_empty = len(list(client.wekan.cards.find({"listId": list_["_id"], "archived": False}))) == 0

            if all_closed and list_is_empty:
                print "all other milestone are closed, closing"
                client.wekan.lists.update({"_id": list_["_id"]}, {"$set": {"archived": True}})

            if request.json["action"] == "deleted":
                client.wekan.bridge_for_milestones.remove({
                    "github_id": request.json["milestone"]["number"],
                    "github_project": project
                })

                # move all cards out in "no milestone" list
                print "deleting action, moving all cards "
                list_ = get_default_list(client, board)
                for card in client.wekan.cards.find({"listId": list_["_id"]}):
                    # TODO update title
                    # should I just uses the "import_pr" here?
                    client.wekan.lists.update({"_id": list_["_id"]}, {"$set": {"listId": list_["_id"]}})

        elif request.json["action"] == "opened":
            # set column state to unarchived
            # assuming the milestone exist
            bridge_milestone = get(client.wekan.bridge_for_milestones, {
                "github_id": request.json["milestone"]["number"],
                "github_project": project
            })
            list_ = get_by_id(client.wekan.lists, bridge_milestone["wekan_id"])
            client.wekan.lists.update({"_id": list_["_id"]}, {"$set": {"archived": False}})

        elif request.json["action"] == "edited":
            print request.json["changes"]

            bridge_milestone = get(client.wekan.bridge_for_milestones, {
                "github_id": request.json["milestone"]["number"],
                "github_project": project
            })

            # only care about title change
            if not request.json["changes"].get("title"):
                return "ok"

            new_title = request.json["milestone"]["title"]
            new_list_title = "%s [MILESTONE]" % new_title
            list_ = get_by_id(client.wekan.lists, bridge_milestone["wekan_id"])

            # if I'm the only milestone on that column rename it
            if len(list(client.wekan.bridge_for_milestones.find({"wekan_id": bridge_milestone["wekan_id"]}))) == 1:
                print "I'm the only milestone on that column rename it"
                print list(client.wekan.bridge_for_milestones.find({"wekan_id": bridge_milestone["wekan_id"]}))
                client.wekan.lists.update({"_id": list_["_id"]}, {"$set": {"title": new_list_title}})

                # rename card: change milestone titles
                for card in client.wekan.cards.find({"listId": list_["_id"]}):
                    old_milestone_card_title = "{%s}" % request.json["changes"]["title"]["from"].lower().replace(" ", "-")
                    new_milestone_card_title = "{%s}" % request.json["milestone"]["title"].lower().replace(" ", "-")
                    title = card["title"].replace(old_milestone_card_title, new_milestone_card_title, 1)
                    print "rename card: '%s' -> '%s'" % (card["title"], title)
                    client.wekan.cards.update({"_id": card["_id"]}, {"$set": {"title": title}})

                return "ok"

            # I'm not the only milestone pointing on that column

            target_list = get_none(client.wekan.lists, {"title": new_list_title})
            print "new_list_title:", new_list_title
            print "target list:", target_list

            board = get_board(client)

            # are they any other column with the same new title?
            if target_list:
                # if so, merge into it
                print "there is one list with the same title, merge into it"
                list_id = target_list["_id"]
            else:
                # else, create new list
                print "no other colum with new title, create a new one", request.json["milestone"]
                sort = 1 + max([x.get("sort", 0) for x in client.wekan.lists.find({"boardId": board["_id"]})])

                print "create new list '%s'" % new_list_title
                list_id = client.wekan.lists.insert({
                    "_id" : generate_id(),
                    "title" : new_list_title,
                    "boardId" : board["_id"],
                    "archived" : False,
                    "createdAt" : datetime.now(),
                    "sort" : sort
                })

                client.wekan.bridge_for_milestones.update({"github_project": bridge_milestone["github_project"], "github_id": bridge_milestone["github_id"]}, {"$set": {"wekan_id": list_id}})

            # move all the milestone cards into the new target list
            for bridge_pr in client.wekan.bridge_for_prs.find({"github_project": project}):
                card = get_by_id(client.wekan.cards, bridge_pr["wekan_id"])

                if card["listId"] == bridge_milestone["wekan_id"]:
                    cards_in_column = list(client.wekan.cards.find({"boardId": board["_id"], "listId": list_}))
                    sort = 1 + (max([x.get("sort", 0) for x in cards_in_column]) if cards_in_column else -1)

                    old_milestone_card_title = "{%s}" % request.json["changes"]["title"]["from"].lower().replace(" ", "-")
                    new_milestone_card_title = "{%s}" % request.json["milestone"]["title"].lower().replace(" ", "-")
                    title = card["title"].replace(old_milestone_card_title, new_milestone_card_title, 1)

                    print "'%s' (%s): %s -> %s [%s]" % (card["title"], card["_id"], bridge_milestone["wekan_id"], list_id, sort)
                    print "rename card '%s' -> '%s'" % (card["title"], title)
                    client.wekan.cards.update({"_id": card["_id"]}, {"$set": {"listId": list_id, "sort": sort, "title": title}})

        else:
            print "unkown action for milestone webhook: '%s'" % request.json["action"]

    elif hook_type == "label":
        # TODO
        pass

    # XXX really need to do that?
    elif hook_type == "user":
        # TODO
        pass

    else:
        print "unsupported hook type: %s" % hook_type

    return "ok"


if __name__ == '__main__':
    app.run(host="0.0.0.0")
