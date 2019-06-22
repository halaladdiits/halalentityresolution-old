import csv
from neo4j import GraphDatabase
from gensim.models import KeyedVectors
import textdistance
import sys

def writecsv(file, string):
    with open(file + '.csv', 'a', encoding="utf-8") as outfile:
        outfile.write(string + "\n")

def createEdgeList(driver, filename):
    print('Create the edge list')
    with driver.session() as session, open("graph/"+filename+".edgelist", "a", encoding='UTF8') as edges_file:

        #create edge manufaktur
        result = session.run("""\
        MATCH (m:ns1__FoodProduct)-[:ns3__hasManufacturer]-(other)
        RETURN id(m) AS source, id(other) AS target
        """)

        writer = csv.writer(edges_file, delimiter=" ")

        for row in result:
            writer.writerow([row["source"], row["target"]])

        #create edge certificates
        result = session.run("""\
                MATCH (m:ns1__FoodProduct)-[:ns1__certificate]-(other)
                RETURN id(m) AS source, id(other) AS target
                """)

        writer = csv.writer(edges_file, delimiter=" ")

        for row in result:
            writer.writerow([row["source"], row["target"]])

        #create edge containsingredient
        # result = session.run("""\
        #                 MATCH (m:ns1__FoodProduct)-[:ns2__containsIngredient]-(other)
        #                 RETURN id(m) AS source, id(other) AS target
        #                 """)
        #
        # writer = csv.writer(edges_file, delimiter=" ")
        #
        # for row in result:
        #     writer.writerow([row["source"], row["target"]])


def writeEmbedtoNode(driver, filename):
    with open("emb/"+filename+".emb", "r") as halal_file, driver.session() as session:
        next(halal_file)
        reader = csv.reader(halal_file, delimiter=" ")

        params = []
        for row in reader:
            entity_id = row[0]
            params.append({
                "id": int(entity_id),
                "embedding": [float(item) for item in row[1:]]
            })

        for param in params:
            print(str(param['id'])+" - "+str(param['embedding']))

        session.run("""\
        UNWIND {params} AS param
        MATCH (m:ns1__FoodProduct) WHERE id(m) = param.id
        SET m.embedding = param.embedding
        """, {"params": params})

def createOwlSameAsRelationQuery(driver, id_source, id_target):
    with driver.session() as session:
        find_entity_query = "MATCH (a:ns1__FoodProduct),(b:ns1__FoodProduct) WHERE id(a) = {} AND id(b) = {} CREATE (a)-[r:owl__sameAs]->(b) RETURN r".format(id_source,id_target)
        session.run(find_entity_query)

def createRdfsSeeAlsoRelationQuery(driver, id_source, id_target):
    with driver.session() as session:
        find_entity_query = "MATCH (a:ns1__FoodProduct),(b:ns1__FoodProduct) WHERE id(a) = {} AND id(b) = {} CREATE (a)-[r:rdfs__seeAlso]->(b) RETURN r".format(id_source,id_target)
        session.run(find_entity_query)

def createLinkCountProperti(driver, id_source, linkcount):
    with driver.session() as session:
        query = "MATCH (a:ns1__FoodProduct) WHERE id(a) = {} SET a.linkCount = {}".format(id_source,linkcount)
        session.run(query)

def setRelationBasedThreshold(driver, model, filename):
    with open(filename, "r") as halal_file, driver.session() as session:
        next(halal_file)
        reader = csv.reader(halal_file, delimiter=" ")

        params = []
        i = 0
        for row in reader:
            if(i == 100):
                sys.exit()

            print("Iteration i = " + str(i))

            entity_id = row[0]
            tupple_source = getEntityDetailsNameAndManuFacture(driver, entity_id)
            ingredientsSource = ""
            tupple_source_with_ingredients = getEntityDetailsNameAndManuFactureAndIngredients(driver, entity_id)
            if(len(tupple_source_with_ingredients) != 0):
                try:
                    for tupple_source_with_ingredient in tupple_source_with_ingredients:
                        ingredientsSource = ingredientsSource + " " + tupple_source_with_ingredient[3]
                except Exception as ex:
                    print("Error when concenating string ingredients = " + str(ex))
                    continue
            similarIds = neo4j_most_similarById(driver, model, entity_id)
            linkcount = 0

            writeFile = False
            listStringWriteToFile = ""
            for similarId in similarIds:

                tupple_target = getEntityDetailsNameAndManuFacture(driver, similarId[0])
                tupple_target_ingredients = getEntityDetailsNameAndManuFactureAndIngredients(driver, similarId[0])
                threshold = 0.9
                if(len(tupple_target_ingredients) == 0):
                    print("Start comparing tanpa ingredients id = "+str(entity_id)+" with "+str(similarId[0]))
                    try:
                        similarityProductName = 0
                        similaritymanufactureName = 0
                        try:
                            similarityProductName = checkSimilarityJaro(tupple_source[0][1], tupple_target[0][1])
                            print("comparing productname = " + str(tupple_source[0][1]) + " with " + tupple_target[0][
                                1] + " hasil similarity = " + str(similarityProductName))
                        except Exception as ex:
                            print("Error comparing product name ex ="+str(ex))
                        try:
                            similaritymanufactureName = checkSimilarityJaro(tupple_source[0][2], tupple_target[0][2])
                            print("comparing manufacture = "+str(tupple_source[0][2])+" with "+tupple_target[0][2]+" hasil similarity = "+str(similaritymanufactureName))
                        except Exception as ex:
                            print("Error comparing manufacture name ex =" + str(ex))

                        similarity = (0.8 * similarityProductName) + (0.2 * similaritymanufactureName)
                        print("Total similarity = " + str(similarity))
                        if(similarity >= threshold):
                            linkcount += 1
                            writeFile = True
                            print("writing owl:sameAs to id source = "+entity_id+" to id target = "+similarId[0]+" with similarity = "
                                  +str(similarity)+" tanpa ingredients")
                            createOwlSameAsRelationQuery(driver, entity_id, similarId[0])
                            stringToWrite = str(entity_id)+"|"+str(tupple_source[0][1])+"|"+str(tupple_source[0][2])+"|null|"+\
                                            str(similarId[0])+"|"+str(tupple_target[0][1])+"|"+str(tupple_target[0][2])+"|null|owlsameAs"
                            
                            listStringWriteToFile = listStringWriteToFile + "\n" + stringToWrite
                            # writecsv("resolutionresults", stringToWrite)
                        elif(similarity > 0.6 and similarity < 0.9):
                            print("Linkcount value = " + str(linkcount))
                            if(linkcount < 5):
                                linkcount += 1
                                print(
                                    "writing rdfs:seeAlso to id source = " + entity_id + " to id target = " + similarId[
                                        0] + " with similarity = "
                                    + str(similarity) + " tanpa ingredients")
                                createRdfsSeeAlsoRelationQuery(driver, entity_id, similarId[0])
                                stringToWrite = str(entity_id) + "|" + str(tupple_source[0][1]) + "|" + str(
                                    tupple_source[0][2]) + "|null|" + \
                                                str(similarId[0]) + "|" + str(tupple_target[0][1]) + "|" + str(
                                    tupple_target[0][2]) + "|null|seeAlso"
                                listStringWriteToFile = listStringWriteToFile + "\n" + stringToWrite
                                # writecsv("resolutionresults", stringToWrite)
                            else:
                                break

                        else:
                            print("Similarity score is not enough = "+str(similarity))

                    except Exception as ex:
                        print("error when trying to comparing entities tanpa ingredients = "+str(ex))
                else:
                    print("Start comparing with ingredients id = " + str(entity_id) + " with " + str(similarId[0]))
                    ingredientsTarget = ""

                    for tupple_target_ingredient in tupple_target_ingredients:
                        try:
                            ingredientsTarget = ingredientsTarget + " " + tupple_target_ingredient[3]
                        except Exception as ex:
                            print("Error when concenating string ingredients = "+str(ex))
                            continue
                    try:

                        similarityProductName = 0
                        similaritymanufactureName = 0
                        try:
                            similarityProductName = checkSimilarityJaro(tupple_source[0][1], tupple_target[0][1])
                            print("comparing productname = " + str(tupple_source[0][1]) + " with " + tupple_target[0][
                                1] + " hasil similarity = " + str(similarityProductName))
                        except Exception as ex:
                            print("Error comparing product name ex =" + str(ex))
                        try:
                            similaritymanufactureName = checkSimilarityJaro(tupple_source[0][2], tupple_target[0][2])
                            print("comparing manufacture = " + str(tupple_source[0][2]) + " with " + tupple_target[0][
                                2] + " hasil similarity = " + str(similaritymanufactureName))
                        except Exception as ex:
                            print("Error comparing manufacture name ex =" + str(ex))
                        try:
                            similarityIngredients = checkSimilarityJaccard(ingredientsSource, ingredientsTarget)
                            print("comparing ingredients = similarity = "+similarityIngredients+" between | "+ingredientsSource+" | with | "+ingredientsTarget)
                        except Exception as ex:
                            print("Error comparing ingredients name ex =" + str(ex))

                        similarity = (0.5 * similarityProductName) + (0.2 * similaritymanufactureName) + (0.3 * similarityIngredients)
                        print("Total similarity = " + str(similarity))
                        if (similarity >= threshold):
                            linkcount += 1
                            writeFile = True
                            print("writing owl:sameAs to id source = " + entity_id + " to id target = " + similarId[
                                0] + " with similarity = " + str(similarity) +" with ingredients")
                            createOwlSameAsRelationQuery(driver, entity_id, similarId[0])
                            stringToWrite = str(entity_id) + "|" + str(tupple_source[0][1]) + "|" + str(
                                tupple_source[0][2]) + "|"+ingredientsSource+"|" + \
                                            str(similarId[0]) + "|" + str(tupple_target[0][1]) + "|" + str(
                                tupple_target[0][2]) + "|"+ingredientsTarget+"|owlsameAs"
                            listStringWriteToFile = listStringWriteToFile + "\n" + stringToWrite
                            # writecsv("resolutionresults", stringToWrite)
                        elif (similarity > 0.6 and similarity < 0.9):

                            print("Linkcount value = "+str(linkcount))

                            if (linkcount < 5):
                                linkcount += 1
                                print(
                                    "writing rdfs:seeAlso to id source = " + entity_id + " to id target = " + similarId[
                                        0] + " with similarity = " + str(similarity) + " with ingredients")

                                createRdfsSeeAlsoRelationQuery(driver, entity_id, similarId[0])
                                stringToWrite = str(entity_id) + "|" + str(tupple_source[0][1]) + "|" + str(
                                    tupple_source[0][2]) + "|" + ingredientsSource + "|" + \
                                                str(similarId[0]) + "|" + str(tupple_target[0][1]) + "|" + str(
                                    tupple_target[0][2]) + "|" + ingredientsTarget + "|seeAlso"
                                listStringWriteToFile = listStringWriteToFile + "\n" + stringToWrite
                                # writecsv("resolutionresults", stringToWrite)
                            else:
                                break
                        else:
                            print("Similarity score is not enough = "+str(similarity))

                    except Exception as ex:
                        print("error when trying to comparing entities with ingredients = "+str(ex))
                    
            if(writeFile == True):
                i += 1
                writecsv("resolutionresults", listStringWriteToFile)
                listStringWriteToFile = ""
            else:
                listStringWriteToFile = ""

            createLinkCountProperti(driver, entity_id, linkcount)

            # params.append({
            #     "id": int(entity_id),
            #     "linkCount": len(similarIds)
            # })

        # for param in params:
        #     print(str(param['id'])+" - "+str(param['linkCount']))
        #
        # session.run("""\
        # UNWIND {params} AS param
        # MATCH (m:ns1__FoodProduct) WHERE id(m) = param.id
        # SET m.linkCount = param.linkCount
        # """, {"params": params})


def setRelationBasedThresholdById(driver, model, entityId):
    entity_id = entityId
    tupple_source = getEntityDetailsNameAndManuFacture(driver, entity_id)
    ingredientsSource = ""
    tupple_source_with_ingredients = getEntityDetailsNameAndManuFactureAndIngredients(driver, entity_id)
    if (len(tupple_source_with_ingredients) != 0):
        try:
            for tupple_source_with_ingredient in tupple_source_with_ingredients:
                ingredientsSource = ingredientsSource + " " + tupple_source_with_ingredient[3]
        except Exception as ex:
            print("Error when concenating string ingredients = " + str(ex))
    similarIds = neo4j_most_similarById(driver, model, entity_id)
    linkcount = 0

    writeFile = False
    listStringWriteToFile = ""
    for similarId in similarIds:

        tupple_target = getEntityDetailsNameAndManuFacture(driver, similarId[0])
        tupple_target_ingredients = getEntityDetailsNameAndManuFactureAndIngredients(driver, similarId[0])
        threshold = 0.9
        if (len(tupple_target_ingredients) == 0):
            print("Start comparing tanpa ingredients id = " + str(entity_id) + " with " + str(similarId[0]))
            try:
                similarityProductName = 0
                similaritymanufactureName = 0
                try:
                    similarityProductName = checkSimilarityJaro(tupple_source[0][1], tupple_target[0][1])
                    print("comparing productname = " + str(tupple_source[0][1]) + " with " + tupple_target[0][
                        1] + " hasil similarity = " + str(similarityProductName))
                except Exception as ex:
                    print("Error comparing product name ex =" + str(ex))
                try:
                    similaritymanufactureName = checkSimilarityJaro(tupple_source[0][2], tupple_target[0][2])
                    print("comparing manufacture = " + str(tupple_source[0][2]) + " with " + tupple_target[0][
                        2] + " hasil similarity = " + str(similaritymanufactureName))
                except Exception as ex:
                    print("Error comparing manufacture name ex =" + str(ex))

                similarity = (0.8 * similarityProductName) + (0.2 * similaritymanufactureName)
                print("Total similarity = " + str(similarity))
                if (similarity >= threshold):
                    linkcount += 1
                    writeFile = True
                    print("writing owl:sameAs to id source = " + entity_id + " to id target = " + similarId[
                        0] + " with similarity = "
                          + str(similarity) + " tanpa ingredients")
                    createOwlSameAsRelationQuery(driver, entity_id, similarId[0])
                    stringToWrite = str(entity_id) + "|" + str(tupple_source[0][1]) + "|" + str(
                        tupple_source[0][2]) + "|null|" + \
                                    str(similarId[0]) + "|" + str(tupple_target[0][1]) + "|" + str(
                        tupple_target[0][2]) + "|null|owlsameAs"

                    listStringWriteToFile = listStringWriteToFile + "\n" + stringToWrite
                    # writecsv("resolutionresults", stringToWrite)
                elif (similarity > 0.6 and similarity < 0.9):
                    print("Linkcount value = " + str(linkcount))
                    if (linkcount < 5):
                        linkcount += 1
                        print(
                            "writing rdfs:seeAlso to id source = " + entity_id + " to id target = " + similarId[
                                0] + " with similarity = "
                            + str(similarity) + " tanpa ingredients")
                        createRdfsSeeAlsoRelationQuery(driver, entity_id, similarId[0])
                        stringToWrite = str(entity_id) + "|" + str(tupple_source[0][1]) + "|" + str(
                            tupple_source[0][2]) + "|null|" + \
                                        str(similarId[0]) + "|" + str(tupple_target[0][1]) + "|" + str(
                            tupple_target[0][2]) + "|null|seeAlso"
                        listStringWriteToFile = listStringWriteToFile + "\n" + stringToWrite
                        # writecsv("resolutionresults", stringToWrite)
                    else:
                        break

                else:
                    print("Similarity score is not enough = " + str(similarity))

            except Exception as ex:
                print("error when trying to comparing entities tanpa ingredients = " + str(ex))
        else:
            print("Start comparing with ingredients id = " + str(entity_id) + " with " + str(similarId[0]))
            ingredientsTarget = ""

            for tupple_target_ingredient in tupple_target_ingredients:
                try:
                    ingredientsTarget = ingredientsTarget + " " + tupple_target_ingredient[3]
                except Exception as ex:
                    print("Error when concenating string ingredients = " + str(ex))
                    continue
            try:

                similarityProductName = 0
                similaritymanufactureName = 0
                try:
                    similarityProductName = checkSimilarityJaro(tupple_source[0][1], tupple_target[0][1])
                    print("comparing productname = " + str(tupple_source[0][1]) + " with " + tupple_target[0][
                        1] + " hasil similarity = " + str(similarityProductName))
                except Exception as ex:
                    print("Error comparing product name ex =" + str(ex))
                try:
                    similaritymanufactureName = checkSimilarityJaro(tupple_source[0][2], tupple_target[0][2])
                    print("comparing manufacture = " + str(tupple_source[0][2]) + " with " + tupple_target[0][
                        2] + " hasil similarity = " + str(similaritymanufactureName))
                except Exception as ex:
                    print("Error comparing manufacture name ex =" + str(ex))
                try:
                    similarityIngredients = checkSimilarityJaccard(ingredientsSource, ingredientsTarget)
                    print(
                        "comparing ingredients = similarity = " + similarityIngredients + " between | " + ingredientsSource + " | with | " + ingredientsTarget)
                except Exception as ex:
                    print("Error comparing ingredients name ex =" + str(ex))

                similarity = (0.5 * similarityProductName) + (0.2 * similaritymanufactureName) + (
                            0.3 * similarityIngredients)
                print("Total similarity = " + str(similarity))
                if (similarity >= threshold):
                    linkcount += 1
                    writeFile = True
                    print("writing owl:sameAs to id source = " + entity_id + " to id target = " + similarId[
                        0] + " with similarity = " + str(similarity) + " with ingredients")
                    createOwlSameAsRelationQuery(driver, entity_id, similarId[0])
                    stringToWrite = str(entity_id) + "|" + str(tupple_source[0][1]) + "|" + str(
                        tupple_source[0][2]) + "|" + ingredientsSource + "|" + \
                                    str(similarId[0]) + "|" + str(tupple_target[0][1]) + "|" + str(
                        tupple_target[0][2]) + "|" + ingredientsTarget + "|owlsameAs"
                    listStringWriteToFile = listStringWriteToFile + "\n" + stringToWrite
                    # writecsv("resolutionresults", stringToWrite)
                elif (similarity > 0.6 and similarity < 0.9):

                    print("Linkcount value = " + str(linkcount))

                    if (linkcount < 5):
                        linkcount += 1
                        print(
                            "writing rdfs:seeAlso to id source = " + entity_id + " to id target = " + similarId[
                                0] + " with similarity = " + str(similarity) + " with ingredients")

                        createRdfsSeeAlsoRelationQuery(driver, entity_id, similarId[0])
                        stringToWrite = str(entity_id) + "|" + str(tupple_source[0][1]) + "|" + str(
                            tupple_source[0][2]) + "|" + ingredientsSource + "|" + \
                                        str(similarId[0]) + "|" + str(tupple_target[0][1]) + "|" + str(
                            tupple_target[0][2]) + "|" + ingredientsTarget + "|seeAlso"
                        listStringWriteToFile = listStringWriteToFile + "\n" + stringToWrite
                        # writecsv("resolutionresults", stringToWrite)
                    else:
                        break
                else:
                    print("Similarity score is not enough = " + str(similarity))

            except Exception as ex:
                print("error when trying to comparing entities with ingredients = " + str(ex))

    if (writeFile == True):
        i += 1
        writecsv("resolutionresults", listStringWriteToFile)
        listStringWriteToFile = ""
    else:
        listStringWriteToFile = ""

    createLinkCountProperti(driver, entity_id, linkcount)

def neo4jgetIdbyLabel(driver, key):
    with driver.session() as session:
        find_entity_query = "MATCH (m:ns1__FoodProduct {rdfs__label: '%s'}) return id(m)" % key

        result = session.run(find_entity_query)
        entity_id = 0
        for r in result:
            entity_id = str(r.value())

        return entity_id


def neo4j_most_similar(driver, model, key):
    with driver.session() as session:
        find_entity_query = "MATCH (m:ns1__FoodProduct {rdfs__label: '%s'}) return id(m)" % key

        result = session.run(find_entity_query)
        for r in result:
            similar_entities = model.most_similar(str(r.value()))
            print("Hasil dari " + key + " with id = " + str(r.value()))
            for s_entity in similar_entities:
                find_entity_query = "MATCH (m:ns1__FoodProduct) where id(m) = %s return m.rdfs__label" % s_entity[0]
                similar_entity_names = session.run(find_entity_query)
                for sm in similar_entity_names:
                    # print the entity name with the cosine similarity
                    # print(sm.value() +" with id "+str(s_entity[0])+" with cousine similarity "+str(s_entity[1]))
                    print(sm.value() +" : "+str(s_entity[1]))

def getEntityDetailsNameAndManuFacture(driver, key):
    with driver.session() as session:
        find_entity_query = "MATCH (m:ns1__FoodProduct)-[:ns3__hasManufacturer]-(other) WHERE id(m) = {} RETURN id(m) AS source, m.rdfs__label AS namaproduk, other.rdfs__label AS target".format(key)

        result = session.run(find_entity_query)
        listTupple = result.values()

    return listTupple

def getEntityDetailsNameAndManuFactureAndIngredients(driver, key):
    with driver.session() as session:
        find_entity_query = """
                           MATCH (m:ns1__FoodProduct)-[:ns3__hasManufacturer]-(manufaktur)
                            MATCH (m)-[:ns2__containsIngredient]-(ingredients)
                            WHERE id(m) = {} RETURN id(m) as id, m.rdfs__label as produk, manufaktur.rdfs__label as manufaktur, ingredients.rdfs__label as ingredient 
                            """.format(key)
        result = session.run(find_entity_query)
        listTupple = result.values()

    return listTupple


def neo4j_most_similarById(driver, model, key):
    global similar_entities
    with driver.session() as session:
        find_entity_query = "MATCH (m:ns1__FoodProduct) WHERE id(m) = %s return id(m)" % key
        result = session.run(find_entity_query)
        for r in result:
            similar_entities = model.most_similar(str(r.value()))

    return similar_entities

def checkSimilarityJaccard(str1, str2):

    str1 = str1.lower()
    str2 = str2.lower()
    similarity = textdistance.jaccard.similarity(str1,str2)
    print("Comparing " + str(str1) + " with " + str(str2)+". Hasil similaritynya = "+str(similarity))
    return similarity

def checkSimilarityJaro(str1, str2):

    str1 = str1.lower()
    str2 = str2.lower()
    similarity = textdistance.jaro_winkler.similarity(str1,str2)
    print("Comparing " + str(str1) + " with " + str(str2)+". Hasil similaritynya = "+str(similarity))
    return similarity

if __name__ == '__main__':

    #uncomment the necessary method based on your task

    host = "bolt://localhost:7687"  # replace this with your neo4j db host
    user = "neo4j"
    password = "123"  # replace this with your neo4j db password

    driver = GraphDatabase.driver(host, auth=(user, password))

    #--Step 1

    ##Create edgelist to process in graph embedding
    # createEdgeList(driver, filename)

    #after creating edge list
    # writeEmbedtoNode(driver, filename)


    #--Setp 2
    #At this step we wxecute graph embedding process to build .emb embedding file
    #./node2vec -i:graph/halalcustomnoingredient.edgelist -o:emb/halalcustomnoingredientconf050570.emb -l:70 -q:0.5 -p:0.5 -dr -v


    filename = 'emb/halalcustomnoingredientconf050570.emb'
    model = KeyedVectors.load_word2vec_format(filename, binary=False)

    #--Step 3
    ##Tes the similar result base on graph embedding process model,
    # neo4j_most_similar(driver, model, 'Cereal Energen Kacang Hijau')
    # neo4j_most_similar(driver, model, 'Energen rasa kacang hijau')
    neo4j_most_similar(driver, model, 'Nissin Wafer Krim Coklat')

    #--Step 4 run entity resolution task by id
    #you can use method setRelationBasedThresholdById or setRelationBasedThreshold to iterate all of id in the .emb file
    # entity_id = neo4jgetIdbyLabel(driver, 'Nissin Wafer Krim Rasa Pisang')
    # setRelationBasedThresholdById(driver, model, filename, entity_id)
    # setRelationBasedThreshold(driver, model, filename)

    ##NOT IMPORTANT
    #Code below is not important, this is just trivial method to test method logic

    ##heck similarity
    # skorsimilarity = checkSimilarity('Kopiko L A Coffee As You Like', 'Kopiko Brown Coffee As You Like')
    # print(str(skorsimilarity))

    ##Get entity detail with product name and manufacture
    # data = getEntityDetailsNameAndManuFacture(driver, 15391)
    # print(data[0][2])


    # createOwlSameAsRelationQuery(driver, 23480, 23047)

    # listTupples = getEntityDetailsNameAndManuFactureAndIngredients(driver, 2209)
    # ingredients = ""
    # for tupple in listTupples:
    #     ingredients = ingredients+" "+ tupple[3]

    # print(str(ingredients))
    # if(len(listTupples) == 0):
    #     print("YES")
    # str1 = "John Farmer Peanut Butter Creamy 27"
    # str2 = "John Farmer Peanut Butter Creamy 02"
    # checkSimilarityJaccard(str1, str2)
    # checkSimilarityJaro(str1, str2)